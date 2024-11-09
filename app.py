from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb.cursors
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
from flask_cors import CORS
import pandas as pd
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config.from_object('config.Config')
mysql = MySQL(app)
app.secret_key = app.config['SECRET_KEY']
socketio = SocketIO(app, cors_allowed_origins="*")
admin_email='basaksoumyadeep04@gmail.com'
games = {}

# Login-required decorator
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
                if(email==admin_email):
                    return redirect(url_for('admin_dashboard'))
                else:
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

@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/users')
def users():
    try:
        # Connect to the database
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Exclude the admin email and fetch other users
          # Replace with actual admin email
        query = """
        SELECT id, email
        FROM Users
        WHERE email != %s
        """
        cursor.execute(query, (admin_email,))
        users = cursor.fetchall()

        # Close the cursor
        cursor.close()

        # Render the HTML template with user data
        return render_template('users.html', users=users)
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return f"An error occurred while fetching user list: {e}", 500




@app.route('/games')
def games():
    try:
        # Connect to the database
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Fetch data with email instead of IDs for winner and loser
        query = """
        SELECT
            gr.id,
            u1.email AS winner_email,
            u2.email AS loser_email
        FROM
            GameResults gr
        JOIN
            Users u1 ON gr.winner_id = u1.id
        JOIN
            Users u2 ON gr.loser_id = u2.id
        WHERE
            u1.email != %s AND u2.email != %s
        """
        cursor.execute(query, (admin_email,admin_email,))
        results = cursor.fetchall()

        # Close the cursor
        cursor.close()

        # Pass the results to the HTML template
        return render_template('games.html', game_results=results)
    
    except Exception as e:
        # Print and return the specific error message
        print(f"An error occurred: {e}")
        return f"An error occurred while fetching game results: {e}", 500

@app.route('/room')
@login_required
def room():
    
    return render_template('room.html', email=session['email'])

@app.route('/game')
@login_required
def game():
    return render_template('game.html')

@socketio.on('join_game')
@login_required
def on_join(data):
    room = data['room']
    username = session.get('email')
    if not username:
        return  
    
    join_room(room)
    
    if room not in games:
        games[room] = {'players': [], 'turn': 0, 'board': [''] * 9, 'completed': False}
    
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

    # Ensure game exists, isn't completed, and it's the player's turn
    if not game:
        emit('error', {'message': 'Game not found.'})
        return

    if game['completed']:
        emit('error', {'message': 'Game is already completed.'})
        return

    # Check if the move is from the correct player
    if player != game['players'][game['turn']]:
        emit('error', {'message': 'Not your turn.'}, room=player)
        return

    # Check if the cell is already occupied
    if game['board'][move_index] != '':
        emit('invalid_move', {'message': 'Cell already taken.'}, room=player)
        return

    # Make the move
    symbol = 'X' if game['turn'] == 0 else 'O'
    game['board'][move_index] = symbol
    emit('move_made', {'index': move_index, 'symbol': symbol}, room=room)

    # Check for a winner after the move
    result = check_winner(game['board'], game['players'][0], game['players'][1],room)
    if result:
        game['completed'] = True
        emit('game_won', {'winner': result['winner']}, room=room)
        update_winner(result['winner'])
        update_loser(result['loser'])
        del games[room]  # Clean up completed game
    else:
        game['turn'] = (game['turn'] + 1) % 2  # Switch turns

def check_winner(board, player1_email, player2_email, room):
    winning_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    
    for a, b, c in winning_combinations:
        if board[a] == board[b] == board[c] and board[a] != '_'and board[a]!='':
            # Determine the winner and loser based on the board state
            winner_email = player1_email if board[a] == 'X' else player2_email
            loser_email = player2_email if board[a] == 'X' else player1_email
            
            # Update the game result in the database
            record_game_result(room, winner_email, loser_email)
            
            return {'winner': winner_email, 'loser': loser_email}
    
    return None  # No winner found

def record_game_result(room, winner_email, loser_email):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        # Fetch winner and loser IDs
        cursor.execute('SELECT id FROM Users WHERE email = %s', (winner_email,))
        winner_id = cursor.fetchone()['id']
        cursor.execute('SELECT id FROM Users WHERE email = %s', (loser_email,))
        loser_id = cursor.fetchone()['id']
        
        # Insert game result into GameResults table
        cursor.execute(
            'INSERT INTO GameResults (game_id, winner_id, loser_id) VALUES (%s, %s, %s)',
            (room, winner_id, loser_id)
        )
        mysql.connection.commit()
    except Exception as e:
        logger.error(f'Error recording game result: {e}')
    finally:
        cursor.close()

'''
def update_winner(winner_email):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT id FROM Users WHERE email = %s', (winner_email,))
    winner_id = cursor.fetchone()['id']
    cursor.execute(
        'UPDATE Leaderboard SET games_won = games_won + 1, total_score = (games_won + 1) / (games_won + games_lost + 1) * 100 WHERE user_id = %s',
        (winner_id,)
    )
    mysql.connection.commit()
    cursor.close()

def update_loser(loser_email):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT id FROM Users WHERE email = %s', (loser_email,))
    loser_id = cursor.fetchone()['id']
    cursor.execute(
        'UPDATE Leaderboard SET games_lost = games_lost + 1, total_score = (games_won) / (games_won + games_lost + 1) * 100 WHERE user_id = %s',
        (loser_id,)
    )
    mysql.connection.commit()
    cursor.close()
'''
def update_winner(winner_email):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch winner's user ID
    cursor.execute('SELECT id, games_won, games_lost FROM Users JOIN Leaderboard ON Users.id = Leaderboard.user_id WHERE email = %s', (winner_email,))
    winner = cursor.fetchone()
    
    # Increment games_won and calculate total_score
    games_won = winner['games_won'] + 1
    total_games = games_won + winner['games_lost']
    total_score = (games_won / total_games) * 100
    
    cursor.execute(
        'UPDATE Leaderboard SET games_won = %s, total_score = %s WHERE user_id = %s',
        (games_won, total_score, winner['id'])
    )
    mysql.connection.commit()
    cursor.close()

def update_loser(loser_email):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch loser's user ID
    cursor.execute('SELECT id, games_won, games_lost FROM Users JOIN Leaderboard ON Users.id = Leaderboard.user_id WHERE email = %s', (loser_email,))
    loser = cursor.fetchone()
    
    # Increment games_lost and calculate total_score
    games_lost = loser['games_lost'] + 1
    total_games = loser['games_won'] + games_lost
    total_score = (loser['games_won'] / total_games) * 100
    
    cursor.execute(
        'UPDATE Leaderboard SET games_lost = %s, total_score = %s WHERE user_id = %s',
        (games_lost, total_score, loser['id'])
    )
    cursor.execute('UPDATE Leaderboard SET games_lost=games_lost-1 WHERE user_id=%s',(loser['id']))
    mysql.connection.commit()
    cursor.close()




@app.route('/admin_leaderboard')
@login_required
def admin_leaderboard():
    update_leaderboard()
    # Connect to the database
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # SQL query to fetch leaderboard data, excluding emails in admin_dashboard
    query = """
    SELECT Users.email, 
           Leaderboard.games_won, 
           Leaderboard.games_lost, 
           Leaderboard.total_score 
    FROM Leaderboard
    JOIN Users ON Leaderboard.user_id = Users.id
    WHERE Users.email != %s
    ORDER BY Leaderboard.total_score DESC
    """
    cursor.execute(query, (admin_email,))
    # cursor.execute(query)
    leaderboard_data = cursor.fetchall()
    
    # Log the leaderboard data
    logger.info("Leaderboard Data: %s", leaderboard_data)
    
    # Close the cursor
    cursor.close()

    # Render the HTML template with leaderboard data
    return render_template('admin_leaderboard.html', leaderboard=leaderboard_data)












@app.route('/leaderboard')
@login_required
def leaderboard():
    update_leaderboard()
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT Users.email, Leaderboard.games_won, Leaderboard.games_lost, Leaderboard.total_score FROM Leaderboard JOIN Users ON Leaderboard.user_id = Users.id ORDER BY Leaderboard.total_score DESC')
    leaderboard_data = cursor.fetchall()
    # df=pd.DataFrame(leaderboard_data)
    # df.to_csv('C:\Users\USER\OneDrive\Desktop\hack\tic_tac_toe\leaderboard.csv')
    logger.info("Leaderboard Data: %s", leaderboard_data)
    cursor.close()
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

def update_leaderboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Reset the Leaderboard
        # cursor.execute('UPDATE Leaderboard SET games_won = 0, games_lost = 0, games_drawn = 0, total_score = 0.00')
        
        # Update wins
        cursor.execute(
            '''
            UPDATE Leaderboard AS lb
            JOIN (
                SELECT winner_id AS user_id, COUNT(*) AS games_won
                FROM GameResults
                GROUP BY winner_id
            ) AS win_counts
            ON lb.user_id = win_counts.user_id
            SET lb.games_won = win_counts.games_won
            '''
        )
        
        # Update losses
        cursor.execute(
            '''
            UPDATE Leaderboard AS lb
            JOIN (
                SELECT loser_id AS user_id, COUNT(*) AS games_lost
                FROM GameResults
                GROUP BY loser_id
            ) AS loss_counts
            ON lb.user_id = loss_counts.user_id
            SET lb.games_lost = loss_counts.games_lost
            '''
        )
        
        # Calculate total games for each user to compute total_score
        cursor.execute(
            '''
            UPDATE Leaderboard
            SET total_score = CASE 
                WHEN games_won + games_lost + games_drawn > 0
                THEN (games_won / (games_won + games_lost + games_drawn)) * 100
                ELSE 0
            END
            '''
        )

        mysql.connection.commit()
    except Exception as e:
        logger.error(f'Error updating leaderboard: {e}')
        mysql.connection.rollback()
    finally:
        cursor.close()


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('home'))

if __name__ == "__main__":
    socketio.run(app, debug=True)