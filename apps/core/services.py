import requests
from django.conf import settings
from .models import Currency

class CurrencyService:
    @staticmethod
    def update_live_rates():
        # Example using a free API
        api_url = "https://open.er-api.com/v6/latest/USD" 
        response = requests.get(api_url).json()
        
        if response.get('result') == 'success':
            rates = response.get('rates')
            for code, rate in rates.items():
                Currency.objects.filter(code=code).update(
                    exchange_rate=rate
                )
            return True
        return False