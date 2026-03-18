<?php
session_start();

require_once 'config.php';
require_once 'FyersClient.php';

$fyersClient = new FyersClient($config);

// --- Handle Logout ---
if (isset($_GET['action']) && $_GET['action'] === 'logout') {
    unset($_SESSION['fyers_access_token']);
    session_destroy();
    header('Location: index.php');
    exit();
}

// --- Handle Callback ---
if (isset($_GET['auth_code'])) {
    $tokenData = $fyersClient->generateToken($_GET['auth_code']);
    if ($tokenData && isset($tokenData['access_token'])) {
        $_SESSION['fyers_access_token'] = $tokenData['access_token'];
        header('Location: index.php');
        exit();
    } else {
        die("Authentication failed. Please try again.");
    }
}

// --- Handle AJAX API Requests ---
if (isset($_GET['action']) || isset($_POST['action'])) {
    header('Content-Type: application/json');
    
    if (!isset($_SESSION['fyers_access_token'])) {
        echo json_encode(['error' => 'User not authenticated']);
        exit();
    }

    $action = $_GET['action'] ?? $_POST['action'] ?? '';

    if ($action === 'get_stocks') {
        $response = $fyersClient->getQuotes();
        if (!$response || $response['code'] != 200 || !isset($response['d'])) {
            echo json_encode(['error' => $response['message'] ?? 'Failed to fetch quotes']);
            exit();
        }

        $stocks_data = [];
        $history_file = 'price_history.json';
        $price_history_cache = file_exists($history_file) ? json_decode(file_get_contents($history_file), true) : [];

        foreach ($response['d'] as $stock) {
            $details = $stock['v'];
            $symbol = $details['short_name'] ?? 'N/A';
            $current_price = $details['lp'] ?? 0;

            $history = $price_history_cache[$symbol] ?? [];
            if (empty($history) || end($history) !== $current_price) {
                $history[] = $current_price;
            }
            if (count($history) > 3) $history = array_slice($history, -3);
            $price_history_cache[$symbol] = $history;

            $suggestion = "Hold";
            $trend_strength = 0.0;

            if (count($history) === 3) {
                if ($history[0] < $history[1] && $history[1] < $history[2]) {
                    $percent = (($history[2] - $history[0]) / $history[0]) * 100;
                    $suggestion = "BUY NOW - " . number_format($percent, 2) . "% Up";
                    $trend_strength = $percent;
                } elseif ($history[0] > $history[1] && $history[1] > $history[2]) {
                    $percent = (($history[0] - $history[2]) / $history[0]) * 100;
                    $suggestion = "SELL NOW - " . number_format($percent, 2) . "% Down";
                    $trend_strength = -$percent;
                }
            }

            $stocks_data[] = [
                'name' => $symbol,
                'price' => $current_price,
                'change' => $details['ch'] ?? 0,
                'percent_change' => $details['chp'] ?? 0,
                'suggestion' => $suggestion,
                'trend_strength' => $trend_strength
            ];
        }

        file_put_contents($history_file, json_encode($price_history_cache));

        $top_buys = array_filter($stocks_data, fn($s) => $s['trend_strength'] > 0);
        usort($top_buys, fn($a, $b) => $b['trend_strength'] <=> $a['trend_strength']);
        $top_sells = array_filter($stocks_data, fn($s) => $s['trend_strength'] < 0);
        usort($top_sells, fn($a, $b) => $a['trend_strength'] <=> $b['trend_strength']);

        echo json_encode([
            'market_status' => 'Open',
            'top_gainers' => array_slice($top_buys, 0, 15),
            'top_losers' => array_slice($top_sells, 0, 15)
        ]);
        exit();
    }

    if ($action === 'get_history') {
        $symbol = $_GET['symbol'] ?? '';
        $response = $fyersClient->getHistory($symbol);
        echo json_encode($response['code'] == 200 ? ['success' => true, 'candles' => $response['candles'] ?? []] : ['success' => false, 'message' => $response['message']]);
        exit();
    }

    if ($action === 'trade') {
        $response = $fyersClient->placeOrder($_POST['symbol'], $_POST['quantity'], $_POST['trade_type']);
        echo json_encode($response['code'] == 200 ? ['success' => true, 'order_id' => $response['id']] : ['success' => false, 'message' => $response['message']]);
        exit();
    }
}

// --- Render UI ---
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Stock Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: sans-serif; background: #f4f4f4; padding: 20px; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .login-box { text-align: center; padding: 50px; }
        .btn { padding: 10px 20px; cursor: pointer; border: none; border-radius: 4px; color: white; font-weight: bold; }
        .buy-btn { background: #27ae60; } .sell-btn { background: #c0392b; } .chart-btn { background: #3498db; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background: #3498db; color: white; }
        .gainer { color: #27ae60; } .loser { color: #c0392b; }
        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
        .modal-content { background: white; margin: 10% auto; padding: 20px; width: 80%; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <?php if (!isset($_SESSION['fyers_access_token'])): ?>
            <div class="login-box">
                <h1>Welcome to Stock Dash</h1>
                <a href="<?php echo $fyersClient->getAuthCodeUrl(); ?>" class="btn chart-btn" style="text-decoration:none;">Login with Fyers</a>
            </div>
        <?php else: ?>
            <div style="display:flex; justify-content:space-between;">
                <h1>Dashboard</h1>
                <a href="index.php?action=logout">Logout</a>
            </div>

            <h2>Top Buys</h2>
            <table id="top-gainers">
                <thead><tr><th>Symbol</th><th>Price</th><th>Change</th><th>%</th><th>Suggestion</th><th>Actions</th></tr></thead>
                <tbody></tbody>
            </table>

            <h2>Top Sells</h2>
            <table id="top-losers">
                <thead><tr><th>Symbol</th><th>Price</th><th>Change</th><th>%</th><th>Suggestion</th><th>Actions</th></tr></thead>
                <tbody></tbody>
            </table>
        <?php endif; ?>
    </div>

    <div id="chartModal" class="modal">
        <div class="modal-content">
            <span onclick="document.getElementById('chartModal').style.display='none'" style="float:right; cursor:pointer;">&times;</span>
            <canvas id="stockChart"></canvas>
        </div>
    </div>

    <script>
        let stockChart = null;

        async function fetchStocks() {
            const res = await fetch('index.php?action=get_stocks');
            const data = await res.json();
            if (data.error) return window.location.reload();
            
            updateTable('top-gainers', data.top_gainers);
            updateTable('top-losers', data.top_losers);
        }

        function updateTable(id, stocks) {
            const tbody = document.querySelector(`#${id} tbody`);
            tbody.innerHTML = '';
            stocks.forEach(s => {
                const row = `<tr>
                    <td>${s.name}</td>
                    <td>₹${s.price.toFixed(2)}</td>
                    <td class="${s.change >= 0 ? 'gainer' : 'loser'}">${s.change.toFixed(2)}</td>
                    <td class="${s.change >= 0 ? 'gainer' : 'loser'}">${s.percent_change.toFixed(2)}%</td>
                    <td>${s.suggestion}</td>
                    <td>
                        <button class="btn chart-btn" onclick="viewChart('${s.name}')">Chart</button>
                        <input type="number" id="qty-${s.name}" value="1" style="width:50px">
                        <button class="btn buy-btn" onclick="trade('${s.name}', 'buy')">Buy</button>
                        <button class="btn sell-btn" onclick="trade('${s.name}', 'sell')">Sell</button>
                    </td>
                </tr>`;
                tbody.innerHTML += row;
            });
        }

        async function viewChart(symbol) {
            document.getElementById('chartModal').style.display = 'block';
            const res = await fetch(`index.php?action=get_history&symbol=${symbol}`);
            const result = await res.json();
            if (!result.success) return alert('Failed to load chart');

            const ctx = document.getElementById('stockChart').getContext('2d');
            if (stockChart) stockChart.destroy();
            stockChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: result.candles.map(c => new Date(c[0]*1000).toLocaleTimeString()),
                    datasets: [{ label: symbol, data: result.candles.map(c => c[4]), borderColor: '#3498db', fill: false }]
                }
            });
        }

        async function trade(symbol, type) {
            const qty = document.getElementById(`qty-${symbol}`).value;
            const formData = new FormData();
            formData.append('action', 'trade');
            formData.append('symbol', symbol);
            formData.append('quantity', qty);
            formData.append('trade_type', type);

            const res = await fetch('index.php', { method: 'POST', body: formData });
            const result = await res.json();
            alert(result.success ? 'Order Placed: ' + result.order_id : 'Error: ' + result.message);
        }

        if (document.getElementById('top-gainers')) {
            fetchStocks();
            setInterval(fetchStocks, 30000);
        }
    </script>
</body>
</html>