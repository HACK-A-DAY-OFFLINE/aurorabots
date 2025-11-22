<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>ESP32 Mapping Dashboard</title>

<style>
    body {
        background: #1b1b1b;
        font-family: Arial, sans-serif;
        margin: 0;
        padding: 0;
        color: #ddd;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
    }

    .container {
        width: 95%;
        max-width: 1250px;
        display: flex;
        gap: 20px;
    }

    .panel {
        width: 300px;
        background: #222;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #444;
    }

    h2 {
        color: #4db6ff;
        text-align: center;
        font-size: 20px;
        margin-bottom: 15px;
    }

    .status-box {
        text-align: center;
        margin-bottom: 20px;
        font-size: 16px;
    }

    #status {
        padding: 5px 12px;
        border-radius: 8px;
        background: #933;
        color: white;
    }

    .sensor-box {
        background: #2b2b2b;
        border: 1px solid #555;
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 20px;
    }

    .sensor-item {
        margin: 6px 0;
        font-size: 15px;
    }

    .label {
        color: #7fcaff;
    }

    .control-box {
        background: #2b2b2b;
        border: 1px solid #555;
        padding: 12px;
        border-radius: 10px;
        margin-top: 20px;
    }

    .control-btn {
        width: 100%;
        padding: 10px;
        font-size: 16px;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        margin-bottom: 10px;
        background: #4db6ff;
        color: #000;
    }
    .stop-btn {
        background: #ff4444;
        color: #fff;
    }
    .reset-btn {
        background: #8e8e8e;
        color: #111;
    }

    input[type=range] {
        width: 100%;
    }

    .map-card {
        flex: 1;
        background: #202020;
        border-radius: 12px;
        padding: 15px;
        border: 1px solid #444;
    }

    canvas {
        background: #111;
        border: 1px solid #555;
        border-radius: 8px;
    }
</style>
</head>

<body>

<div class="container">

    <div class="panel">
        <h2>Robot Status</h2>

        <div class="status-box">
            Connection: <span id="status">Disconnected</span>
        </div>

        <h2>Sensors</h2>
        <div class="sensor-box">
            <div class="sensor-item"><span class="label">Front:</span> <span id="sf">--</span> cm</div>
            <div class="sensor-item"><span class="label">Right:</span> <span id="sr">--</span> cm</div>
            <div class="sensor-item"><span class="label">Back:</span> <span id="sb">--</span> cm</div>
            <div class="sensor-item"><span class="label">Left:</span> <span id="sl">--</span> cm</div>
        </div>

        <h2>Controls</h2>
        <div class="control-box">
            <button id="startBtn" class="control-btn">Start Mapping</button>
            <button id="stopBtn" class="control-btn stop-btn">Stop Mapping</button>
            <button id="resetBtn" class="control-btn reset-btn">Reset Map</button>

            <br><br>
            <label class="label">Movement Speed</label>
            <input type="range" id="speedSlider" min="0" max="5" value="1">

            <br><br>

            <label class="label">Trail:</label>
            <input type="checkbox" id="trailToggle" checked>
        </div>

    </div>

    <div class="map-card">
        <h2>2D Mapping</h2>
        <canvas id="map" width="600" height="600"></canvas>
    </div>

</div>

<script>
let ws;
let mappingActive = true;
let showTrail = true;
let speed = 1;

let canvas = document.getElementById("map");
let ctx = canvas.getContext("2d");

let car = {
    x: 300,
    y: 300,
    path: []
};

let gridSize = 30;

//DRAWING
function drawGrid() {
    ctx.strokeStyle = "#222";
    for (let x = 0; x < 600; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, 600);
        ctx.stroke();
    }
    for (let y = 0; y < 600; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(600, y);
        ctx.stroke();
    }
}

function drawCar() {
    ctx.fillStyle = "#4db6ff";
    ctx.beginPath();
    ctx.arc(car.x, car.y, 6, 0, Math.PI * 2);
    ctx.fill();
}

function drawPath() {
    if (!showTrail) return;
    ctx.strokeStyle = "#888";
    ctx.lineWidth = 2;

    ctx.beginPath();
    for (let i = 0; i < car.path.length - 1; i++) {
        ctx.moveTo(car.path[i].x, car.path[i].y);
        ctx.lineTo(car.path[i + 1].x, car.path[i + 1].y);
    }
    ctx.stroke();
}

function drawLine(distance, angleDeg) {
    if (distance < 0) return;

    let angle = (angleDeg - 90) * Math.PI / 180;
    let endX = car.x + distance * Math.cos(angle);
    let endY = car.y + distance * Math.sin(angle);

    ctx.strokeStyle = "#4caf50";
    ctx.beginPath();
    ctx.moveTo(car.x, car.y);
    ctx.lineTo(endX, endY);
    ctx.stroke();

    ctx.fillStyle = "#ff3333";
    ctx.beginPath();
    ctx.arc(endX, endY, 3, 0, Math.PI * 2);
    ctx.fill();
}

// ------------------- WEBSOCKET -----------------------
function connectWebSocket() {
    ws = new WebSocket("ws://192.168.4.1:81/");

    ws.onopen = () => {
        document.getElementById("status").style.background = "#1a7";
        document.getElementById("status").innerText = "Connected";
    };

    ws.onclose = () => {
        document.getElementById("status").style.background = "#933";
        document.getElementById("status").innerText = "Disconnected";
        setTimeout(connectWebSocket, 1000);
    };

    ws.onmessage = event => {
        if (!mappingActive) return;

        let data = JSON.parse(event.data);

        document.getElementById("sf").innerText = data.front;
        document.getElementById("sr").innerText = data.right;
        document.getElementById("sb").innerText = data.back;
        document.getElementById("sl").innerText = data.left;

        updateMap(data);
    };
}

// ----------- SEND COMMANDS TO ESP32 ---------------
function sendCmd(obj) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(obj));
}

// ------------------- CONTROL BINDINGS -----------------------
document.getElementById("startBtn").onclick = () => {
    mappingActive = true;
    sendCmd({cmd: "start"});
};

document.getElementById("stopBtn").onclick = () => {
    mappingActive = false;
    sendCmd({cmd: "stop"});
};

document.getElementById("resetBtn").onclick = () => {
    car.x = 300;
    car.y = 300;
    car.path = [];
    sendCmd({cmd: "reset"});
};

document.getElementById("speedSlider").oninput = e => {
    speed = Number(e.target.value);
    sendCmd({speed: speed});
};

document.getElementById("trailToggle").onchange = e => {
    showTrail = e.target.checked;
};

//MAP UPDATE
function updateMap(data) {
    ctx.clearRect(0, 0, 600, 600);

    drawGrid();
    drawPath();
    drawCar();

    drawLine(data.front, 0);
    drawLine(data.right, 90);
    drawLine(data.back, 180);
    drawLine(data.left, 270);

    // movement simulation
    car.y -= speed;
    car.path.push({ x: car.x, y: car.y });

    if (car.path.length > 500) car.path.shift();
}

connectWebSocket();
</script>

</body>
</html>
