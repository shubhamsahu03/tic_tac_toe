// Wait for the DOM content to be fully loaded
document.addEventListener("DOMContentLoaded", function() {
    // Check if Socket.IO library is available and the socket is not already initialized
    if (typeof io !== 'undefined' && typeof socket === 'undefined') {
        // Initialize the socket connection
        var socket = io.connect(window.location.origin);

        // Socket connection successful
        socket.on('connect', function() {
            console.log('Connected to server');
        });

        // Listen for game updates from the server
        socket.on('game_update', function(data) {
            console.log('Game update received:', data);
            updateBoard(data.boardState);  // Assuming data contains board state
        });

        // Listen for game winner event
        socket.on('game_winner', function(data) {
            alert('Winner: ' + data.winner);
        });

        // Attach socket to window object to avoid re-initializing
        window.socket = socket;
    }
});

// Function to emit a move event
function makeMove(cellIndex) {
    if (window.socket) {
        console.log('Player clicked on cell ' + cellIndex);
        window.socket.emit('make_move', { cell: cellIndex });

        // Disable the clicked cell or update UI
        document.getElementById('cell-' + cellIndex).classList.add('disabled');
    } else {
        console.error("Socket connection not initialized.");
    }
}

// Update the game board visually based on board state
function updateBoard(boardState) {
    for (let i = 0; i < 9; i++) {
        const cell = document.getElementById('cell-' + i);
        cell.textContent = boardState[i] || '';
        cell.classList.remove('disabled');
    }
}

// Reset the game on server and clear the board
function resetGame() {
    if (window.socket) {
        window.socket.emit('reset_game');
        
        document.querySelectorAll('.cell').forEach(cell => {
            cell.textContent = '';
            cell.classList.remove('disabled');
        });
    } else {
        console.error("Socket connection not initialized.");
    }
}
