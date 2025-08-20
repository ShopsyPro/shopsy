import os
import requests
import hashlib
import base64
import json
from typing import Dict, Any

class CryptomusClient:
    """
    Secure client for interacting with the Cryptomus payment gateway.
    Handles payment creation, webhook signature verification, and supported currencies/networks.
    """
    def __init__(self):
        self.api_key = os.getenv('CRYPTOMUS_API_KEY', 'YOUR_API_KEY')
        self.merchant_id = os.getenv('CRYPTOMUS_MERCHANT_ID', 'YOUR_MERCHANT_ID')
        self.api_url = 'https://api.cryptomus.com/v1/payment'
        self.webhook_secret = os.getenv('CRYPTOMUS_WEBHOOK_SECRET', 'YOUR_WEBHOOK_SECRET')
        self.default_currency = os.getenv('CRYPTOMUS_DEFAULT_CURRENCY', 'USDT')
        self.default_network = os.getenv('CRYPTOMUS_DEFAULT_NETWORK', 'bep20')

    def create_payment(self, amount: float, order_id: str, currency: str = None, to_currency: str = None, network: str = None, callback_url: str = None, buyer_email: str = None, url_return: str = None, url_success: str = None) -> Dict[str, Any]:
        """
        Create a payment invoice on Cryptomus.
        """
        payload = {
            'amount': str(amount),
            'currency': str(currency or self.default_currency or ''),
            'order_id': str(order_id or ''),
            'is_payment_multiple': False,  # Do not allow multiple payments
            'merchant_id': str(self.merchant_id or ''),
        }
        if to_currency:
            payload['to_currency'] = str(to_currency)
        if network:
            payload['network'] = str(network)
        if callback_url:
            payload['url_callback'] = str(callback_url)
        if url_return:
            payload['url_return'] = str(url_return)
        if url_success:
            payload['url_success'] = str(url_success)
        if buyer_email:
            payload['email'] = str(buyer_email)
        json_body = json.dumps(payload, separators=(',', ':'))
        sign = self._generate_signature(json_body)
        headers = {
            'merchant': self.merchant_id,
            'sign': sign,
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'api-key': self.api_key
        }
        response = requests.post(self.api_url, data=json_body, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        """
        Verify the MD5(base64(json_encode(payload)) + API_KEY) signature of a webhook request.
        """
        try:
            # Convert payload to JSON string with proper escaping
            json_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
            # Encode to base64
            b64 = base64.b64encode(json_str.encode('utf-8')).decode()
            # Create hash with API key
            expected = hashlib.md5((b64 + self.api_key).encode()).hexdigest()
            
            # Debug logging (remove in production)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Webhook signature verification: received={signature}, expected={expected}, api_key_length={len(self.api_key)}")
            
            return expected == signature
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    def _generate_signature(self, json_body: str) -> str:
        """
        Generate MD5(base64(json_body) + API_KEY) signature for Cryptomus API requests.
        """
        b64 = base64.b64encode(json_body.encode()).decode()
        return hashlib.md5((b64 + self.api_key).encode()).hexdigest()

    def get_supported_currencies(self) -> Dict[str, Any]:
        """
        Return a static or cached list of supported currencies/networks (could be extended to fetch from API).
        """
        return {
            'USDT': ['bep20', 'trc20', 'erc20'],
            'LTC': ['litecoin'],
            'BTC': ['bitcoin'],
            'ETH': ['erc20'],
            'TRX': ['trc20'],
            # Add more as needed
        }

    def get_invoice_qr(self, uuid: str) -> str:
        """
        Fetch a base64 PNG QR code for the given invoice UUID.
        Returns the image data URI string.
        """
        url = 'https://api.cryptomus.com/v1/payment/qr'
        payload = {'merchant_payment_uuid': uuid}
        json_body = json.dumps(payload, separators=(',', ':'))
        sign = self._generate_signature(json_body)
        headers = {
            'merchant': self.merchant_id,
            'sign': sign,
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'api-key': self.api_key
        }
        response = requests.post(url, data=json_body, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('result', {}).get('image')

    def get_payment_info(self, uuid: str) -> dict:
        """
        Fetch payment info for the given invoice UUID.
        Returns the full info dict.
        """
        url = 'https://api.cryptomus.com/v1/payment/info'
        payload = {'uuid': uuid}
        json_body = json.dumps(payload, separators=(',', ':'))
        sign = self._generate_signature(json_body)
        headers = {
            'merchant': self.merchant_id,
            'sign': sign,
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'api-key': self.api_key
        }
        response = requests.post(url, data=json_body, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get('result', {}) 