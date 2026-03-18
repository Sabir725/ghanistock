<?php

class FyersClient
{
    protected $clientId;
    protected $secretKey;
    protected $redirectUri;
    protected $apiBaseUri;
    protected $stocksToTrack;

    public function __construct($config)
    {
        $this->clientId = $config['client_id'];
        $this->secretKey = $config['secret_key'];
        $this->redirectUri = $config['redirect_uri'];
        $this->apiBaseUri = $config['api_base_uri'];
        $this->stocksToTrack = $config['stocks_to_track'];
    }

    public function getAuthCodeUrl()
    {
        $sessionId = session_id();
        return "https://api-t1.fyers.in/api/v3/generate-authcode?client_id={$this->clientId}&redirect_uri={$this->redirectUri}&response_type=code&state={$sessionId}";
    }

    public function generateToken($authCode)
    {
        $appIdHash = hash('sha256', "{$this->clientId}:{$this->secretKey}");
        $url = $this->apiBaseUri . 'validate-authcode';

        $payload = json_encode([
            'grant_type' => 'authorization_code',
            'appIdHash' => $appIdHash,
            'code' => $authCode,
        ]);

        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
        
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode === 200) {
            return json_decode($response, true);
        }

        return null;
    }

    protected function getAuthenticatedHeaders()
    {
        $accessToken = $_SESSION['fyers_access_token'] ?? '';
        return [
            'Authorization: ' . $this->clientId . ':' . $accessToken,
            'Content-Type: application/json'
        ];
    }

    public function getQuotes()
    {
        $symbols = implode(',', $this->stocksToTrack);
        $url = $this->apiBaseUri . 'quotes?symbols=' . urlencode($symbols);

        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $this->getAuthenticatedHeaders());
        
        $response = curl_exec($ch);
        curl_close($ch);

        return json_decode($response, true);
    }

    public function getHistory($symbol)
    {
        $today = date('Y-m-d');
        $symbolBase = str_replace('-EQ', '', $symbol);
        $finalSymbol = "NSE:{$symbolBase}-EQ";

        $params = http_build_query([
            'symbol' => $finalSymbol,
            'resolution' => '5',
            'date_format' => '1',
            'range_from' => $today,
            'range_to' => $today,
            'cont_flag' => '1'
        ]);

        $url = $this->apiBaseUri . 'history?' . $params;

        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $this->getAuthenticatedHeaders());
        
        $response = curl_exec($ch);
        curl_close($ch);

        return json_decode($response, true);
    }

    public function placeOrder($symbol, $quantity, $action)
    {
        $url = $this->apiBaseUri . 'orders';
        $symbolBase = str_replace('-EQ', '', $symbol);
        $finalSymbol = "NSE:{$symbolBase}-EQ";

        $payload = json_encode([
            'symbol' => $finalSymbol,
            'qty' => (int)$quantity,
            'type' => 2, // Market Order
            'side' => $action === 'buy' ? 1 : -1,
            'productType' => 'INTRADAY',
            'limitPrice' => 0,
            'stopPrice' => 0,
            'validity' => 'DAY',
            'disclosedQty' => 0,
            'offlineOrder' => 'False'
        ]);

        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $this->getAuthenticatedHeaders());
        
        $response = curl_exec($ch);
        curl_close($ch);

        return json_decode($response, true);
    }
}