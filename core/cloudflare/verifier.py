import requests
import logging
from typing import Dict, Any
from .config import CloudflareConfig

logger = logging.getLogger(__name__)

class CloudflareVerifier:
    """Cloudflare Turnstile verification utility"""
    
    @staticmethod
    def verify_token(token: str, remote_ip: str = None) -> Dict[str, Any]:
        """
        Verify Cloudflare Turnstile token
        
        Args:
            token: The Turnstile token from the frontend
            remote_ip: Optional remote IP address
            
        Returns:
            Dict containing verification result
        """
        if not CloudflareConfig.is_configured():
            logger.error("Cloudflare Turnstile not configured")
            return {
                'success': False,
                'error': 'Captcha verification not configured'
            }
        
        if not token:
            return {
                'success': False,
                'error': 'No captcha token provided'
            }
        
        try:
            # Prepare verification request
            data = {
                'secret': CloudflareConfig.get_secret_key(),
                'response': token
            }
            
            if remote_ip:
                data['remoteip'] = remote_ip
            
            # Make verification request
            response = requests.post(
                CloudflareConfig.get_verify_url(),
                data=data,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Cloudflare API returned status {response.status_code}")
                return {
                    'success': False,
                    'error': 'Captcha verification failed'
                }
            
            result = response.json()
            
            if result.get('success'):
                logger.info("Cloudflare Turnstile verification successful")
                return {
                    'success': True,
                    'challenge_ts': result.get('challenge_ts'),
                    'hostname': result.get('hostname')
                }
            else:
                error_codes = result.get('error-codes', [])
                logger.warning(f"Cloudflare Turnstile verification failed: {error_codes}")
                return {
                    'success': False,
                    'error': 'Captcha verification failed',
                    'error_codes': error_codes
                }
                
        except requests.exceptions.Timeout:
            logger.error("Cloudflare verification timeout")
            return {
                'success': False,
                'error': 'Captcha verification timeout'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloudflare verification request failed: {e}")
            return {
                'success': False,
                'error': 'Captcha verification failed'
            }
        except Exception as e:
            logger.error(f"Unexpected error in captcha verification: {e}")
            return {
                'success': False,
                'error': 'Captcha verification failed'
            }
