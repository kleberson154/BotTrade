import logging
import os
import sys
import io
import json
from datetime import datetime

class TradeDecisionLogger:
    """Logger estruturado para decisões de trade (aceitação/rejeição)"""
    
    def __init__(self):
        # Setup do logger estruturado
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        if sys.stdout.encoding != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
        # Logger para decisões estruturadas
        self.logger = logging.getLogger("TradeDecisions")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # Handler para arquivo (JSON estruturado)
            file_handler = logging.FileHandler('logs/trade_decisions.log', encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def log_decision(self, decision_data):
        """
        Log uma decisão de trade estruturada.
        
        Args:
            decision_data (dict): {
                'timestamp': datetime,
                'symbol': str,
                'status': 'ACEITADO' ou 'REJEITADO',
                'signal': 'BUY', 'SELL', 'HOLD',
                'reason': str (motivo principal),
                'details': str (detalhes adicionais),
                'indicators': {
                    'adx': float,
                    'rsi': float,
                    'atr_pct': float,
                    'volume': float,
                    'regime': str
                },
                'price': float (preço atual),
                'entry_details': dict (apenas para ACEITADO) {
                    'sl_price': float,
                    'tp_prices': [float, float, float],
                    'qty': float,
                    'rr_ratio': float,
                    'score': dict
                }
            }
        """
        try:
            # Formato estruturado JSON para fácil parsing
            entry = {
                'timestamp': decision_data.get('timestamp', datetime.now()).isoformat(),
                'symbol': decision_data.get('symbol', 'N/A'),
                'status': decision_data.get('status', 'DESCONHECIDO'),
                'signal': decision_data.get('signal', 'HOLD'),
                'reason': decision_data.get('reason', 'N/A'),
                'details': decision_data.get('details', ''),
                'price': float(decision_data.get('price', 0)),
                'indicators': {
                    'adx': float(decision_data.get('indicators', {}).get('adx', 0)),
                    'rsi': float(decision_data.get('indicators', {}).get('rsi', 0)),
                    'atr_pct': float(decision_data.get('indicators', {}).get('atr_pct', 0)),
                    'volume': float(decision_data.get('indicators', {}).get('volume', 0)),
                    'regime': str(decision_data.get('indicators', {}).get('regime', 'NORMAL'))
                }
            }
            
            # Adicionar detalhes de entrada (se aceito)
            if decision_data.get('entry_details'):
                entry['entry_details'] = decision_data['entry_details']
            
            # Log estruturado
            log_entry = json.dumps(entry, ensure_ascii=False)
            self.logger.info(log_entry)
            
        except Exception as e:
            self.logger.error(f"Erro ao logar decisão: {e}")
    
    def log_acceptance(self, symbol, price, sl_price, tp_prices, qty, rr_ratio, 
                      score_result, indicators, regime):
        """Log de trade ACEITO com detalhes completos"""
        decision_data = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'status': 'ACEITADO',
            'signal': 'BUY/SELL',  # Será preenchido pelo chamador
            'reason': 'Todos os critérios validados com sucesso',
            'details': f'Trade aceito para entrada em {symbol}',
            'price': price,
            'indicators': {
                'adx': indicators.get('adx', 0),
                'rsi': indicators.get('rsi', 0),
                'atr_pct': indicators.get('atr_pct', 0),
                'volume': indicators.get('volume', 0),
                'regime': regime
            },
            'entry_details': {
                'entry_price': price,
                'sl_price': sl_price,
                'tp_prices': tp_prices,
                'qty': qty,
                'rr_ratio': rr_ratio,
                'score': score_result if isinstance(score_result, dict) else {
                    'score': score_result.get('score') if hasattr(score_result, 'get') else 0,
                    'total': score_result.get('total_indicators') if hasattr(score_result, 'get') else 0,
                    'min_required': score_result.get('min_required') if hasattr(score_result, 'get') else 0
                }
            }
        }
        self.log_decision(decision_data)
    
    def log_rejection(self, symbol, signal, reason, details, indicators, price, regime):
        """Log de trade REJEITADO com motivo"""
        decision_data = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'status': 'REJEITADO',
            'signal': signal,
            'reason': reason,
            'details': details,
            'price': price,
            'indicators': {
                'adx': indicators.get('adx', 0),
                'rsi': indicators.get('rsi', 0),
                'atr_pct': indicators.get('atr_pct', 0),
                'volume': indicators.get('volume', 0),
                'regime': regime
            }
        }
        self.log_decision(decision_data)


# Logger global
trade_decision_logger = TradeDecisionLogger()
