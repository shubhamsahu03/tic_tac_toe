from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb.cursors
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config.from_object('config.Config')
mysql = MySQL(app)
app.secret_key = app.config['SECRET_KEY']
socketio = SocketIO(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute('INSERT INTO Users (email, password) VALUES (%s, %s)', (email, hashed_password))
            mysql.connection.commit()

            # Create an entry in the Leaderboard table with initial values
            cursor.execute('SELECT id FROM Users WHERE email = %s', (email,))
            user = cursor.fetchone()
            cursor.execute('INSERT INTO Leaderboard (user_id, games_won, games_lost, games_drawn, total_score) VALUES (%s, 0, 0, 0, 0)', (user['id'],))
            mysql.connection.commit()
            
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
        except MySQLdb.IntegrityError:
            flash('Email already registered. Please log in.')
            return redirect(url_for('login'))
        finally:
            cursor.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute('SELECT * FROM Users WHERE email = %s', (email,))
            user = cursor.fetchone()
        
            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['email'] = user['email']
                session['user_id'] = user['id']
                
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Incorrect email or password', 'danger')
        finally:
            cursor.close()
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', email=session['email'])

@app.route('/room')
@login_required
def room():
    return render_template('room.html', email=session['email'])

@app.route('/game')
@login_required
def game():
    return render_template('game.html')

games = {}

@socketio.on('join_game')
def on_join(data):
    room = data['room']
    username = session.get('email')
    if not username:
        return  
    
    join_room(room)
    
    if room not in games:
        games[room] = {'players': [], 'turn': 0, 'board': [''] * 9}
    
    game = games[room]
    if username not in game['players']:
        game['players'].append(username)
    
    emit('update_room', {'players': game['players']}, room=room)
    
    if len(game['players']) == 2:
        emit('game_start', {'players': game['players']}, room=room)
@socketio.on('make_move')
def on_move(data):
    room = data['room']
    move_index = data['move']
    player = session.get('email')
    game = games.get(room)

    if game and player == game['players'][game['turn']]:
        if game['board'][move_index] == '':
            symbol = 'X' if game['turn'] == 0 else 'O'
            game['board'][move_index] = symbol
            emit('move_made', {'index': move_index, 'symbol': symbol}, room=room)
            
            # Use check_winner to get the winner and loser
            result = check_winner(game['board'], game['players'][0], game['players'][1])
            if result:
                emit('game_won', {'winner': result['winner']}, room=room)
                
                # Update leaderboard for both winner and loser
                update_leaderboard(result['winner'], result='win')  # Winner's record
                update_leaderboard(result['loser'], result='loss')  # Loser's record
                
                # Remove the game from the active games
                del games[room]
                
                # Redirect to dashboard (optional)
                return redirect(url_for('dashboard'))
            else:
                # Switch turn to the other player
                game['turn'] = (game['turn'] + 1) % 2
        else:
            emit('invalid_move', {'message': 'Cell already taken.'}, room=player)


def check_winner(board, player1_email, player2_email):
    winning_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    
    for a, b, c in winning_combinations:
        if board[a] == board[b] == board[c] and board[a] != '':
            winner = player1_email if board[a] == 'X' else player2_email
            loser = player2_email if board[a] == 'X' else player1_email
            return {'winner': winner, 'loser': loser}
    
    return None  # No winner yet


def update_leaderboard(winner_email, result):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch user id based on email for winner
    cursor.execute('SELECT id FROM Users WHERE email = %s', (winner_email,))
    winner = cursor.fetchone()
    winner_id = winner['id']
    
    # Get the current leaderboard record for the winner
    cursor.execute('SELECT * FROM Leaderboard WHERE user_id = %s', (winner_id,))
    leaderboard_winner = cursor.fetchone()
    
    # Update the winner's record
    if leaderboard_winner:
        if result == 'win':
            cursor.execute('UPDATE Leaderboard SET games_won = games_won + 1, total_score = 4 * (games_won + 1) - games_lost WHERE user_id = %s', (winner_id,))
        elif result == 'loss':
            cursor.execute('UPDATE Leaderboard SET games_lost = games_lost + 1, total_score = GREATEST(0, total_score - 1) WHERE user_id = %s', (winner_id,))
    else:
        # Create a new record if no entry exists for winner
        if result == 'win':
            cursor.execute('INSERT INTO Leaderboard (user_id, games_won, games_lost, games_drawn, total_score) VALUES (%s, 1, 0, 0, 4)', (winner_id,))
        elif result == 'loss':
            cursor.execute('INSERT INTO Leaderboard (user_id, games_won, games_lost, games_drawn, total_score) VALUES (%s, 0, 1, 0, 0)', (winner_id,))
    
    # Now handle the loser (opponent) logic
    loser_email = winner_email
    if result == 'win':
        # Opposite user is the loser
        cursor.execute('SELECT email FROM Users WHERE email != %s LIMIT 1', (winner_email,))
        loser = cursor.fetchone()
        loser_email = loser['email']
    
    cursor.execute('SELECT id FROM Users WHERE email = %s', (loser_email,))
    loser = cursor.fetchone()
    loser_id = loser['id']
    
    cursor.execute('SELECT * FROM Leaderboard WHERE user_id = %s', (loser_id,))
    leaderboard_loser = cursor.fetchone()
    
    if leaderboard_loser:
        if result == 'loss':
            cursor.execute('UPDATE Leaderboard SET games_lost = games_lost + 1, total_score = GREATEST(0, total_score - 1) WHERE user_id = %s', (loser_id,))
        elif result == 'win':
            cursor.execute('UPDATE Leaderboard SET games_won = games_won + 1, total_score = 4 * (games_won + 1) - games_lost WHERE user_id = %s', (loser_id,))
    else:
        # Create a new record if no entry exists for loser
        if result == 'loss':
            cursor.execute('INSERT INTO Leaderboard (user_id, games_won, games_lost, games_drawn, total_score) VALUES (%s, 0, 1, 0, 0)', (loser_id,))
        elif result == 'win':
            cursor.execute('INSERT INTO Leaderboard (user_id, games_won, games_lost, games_drawn, total_score) VALUES (%s, 1, 0, 0, 4)', (loser_id,))
    
    mysql.connection.commit()
    cursor.close()


@app.route('/leaderboard')
@login_required
def leaderboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT Users.email, Leaderboard.games_won, Leaderboard.total_score FROM Leaderboard JOIN Users ON Leaderboard.user_id = Users.id ORDER BY Leaderboard.total_score DESC')
    leaderboard_data = cursor.fetchall()
    cursor.close()
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('home'))

if __name__ == "__main__":
    socketio.run(app, debug=True)
