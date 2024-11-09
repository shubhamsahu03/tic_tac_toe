document.addEventListener("DOMContentLoaded", function() {
    const room = prompt("Enter room name:");
    const socket = io.connect(window.location.origin);
    const playerSymbol = {};

    // Join the room
    socket.emit('join_game', { room: room });

    socket.on('update_room', (data) => {
        document.getElementById("players").innerHTML = "Players in room: " + data.players.join(", ");
    });

    socket.on('game_start', (data) => {
        const [player1, player2] = data.players;
        playerSymbol[player1] = 'X';
        playerSymbol[player2] = 'O';
        document.getElementById("status").innerHTML = "Game started! Your symbol: " + playerSymbol[sessionEmail];
    });

    socket.on('move_made', (data) => {
        const cell = document.getElementById(`cell-${data.index}`);
        cell.innerText = data.symbol;
    });

   // Assuming you have SocketIO connected
socket.on('game_won', function(data) {
    const winner = data.winner;
    
    // Display the winner message
    alert(`Game Over! The winner is ${winner}`);
    
    // Optional: Reload the leaderboard after 2 seconds
    setTimeout(function() {
        window.location.href = "/leaderboard"; // Or make an AJAX call to refresh the leaderboard
    }, 2000);
});


    // Emit move
    function makeMove(cellIndex) {
        socket.emit('make_move', { room: room, move: cellIndex });
    }

    // Attach click listeners to cells
    for (let i = 0; i < 9; i++) {
        document.getElementById(`cell-${i}`).addEventListener("click", function() {
            makeMove(i);
        });
    }
});
