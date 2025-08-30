# utils/email_sender.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

class EmailNotifier:
    def __init__(self, smtp_host='smtp.gmail.com', smtp_port=587):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = os.environ.get('EMAIL_SENDER', 'your-email@gmail.com')
        self.sender_password = os.environ.get('EMAIL_PASSWORD', 'your-app-password')
        
    def send_anomaly_alert(self, recipient_email, user_name, sensor_type, value, threshold):
        """Invia un'email di notifica per anomalia rilevata"""
        
        subject = f"⚠️ Anomalia Rilevata - {user_name}"
        
        # Crea il messaggio HTML
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 20px; border-radius: 5px;">
                    <h2 style="color: #721c24;">⚠️ Anomalia Rilevata nel Sistema di Monitoraggio</h2>
                    
                    <p><strong>Utente:</strong> {user_name}</p>
                    <p><strong>Sensore:</strong> {self.get_sensor_name(sensor_type)}</p>
                    <p><strong>Valore Rilevato:</strong> <span style="color: red; font-size: 1.2em;">{value:.2f}</span></p>
                    <p><strong>Soglia Superata:</strong> {threshold:.2f}</p>
                    <p><strong>Data/Ora:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                    
                    <hr>
                    
                    <p style="margin-top: 20px;">
                        <strong>Azione Consigliata:</strong><br>
                        Si consiglia di verificare lo stato del paziente e contattarlo se necessario.
                    </p>
                    
                    <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                        Questo è un messaggio automatico dal Sistema di Monitoraggio IoT.<br>
                        Per maggiori dettagli, accedi alla <a href="http://your-server.com/dashboard">dashboard</a>.
                    </p>
                </div>
            </body>
        </html>
        """
        
        # Versione testo semplice
        text_body = f"""
        ANOMALIA RILEVATA - {user_name}
        
        Sensore: {self.get_sensor_name(sensor_type)}
        Valore Rilevato: {value:.2f}
        Soglia Superata: {threshold:.2f}
        Data/Ora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        
        Si consiglia di verificare lo stato del paziente.
        """
        
        try:
            self.send_email(recipient_email, subject, text_body, html_body)
            return True
        except Exception as e:
            print(f"Errore invio email: {e}")
            return False
    
    def send_daily_report(self, recipient_email, report_data):
        """Invia un report giornaliero con le statistiche"""
        
        subject = f"📊 Report Giornaliero - {datetime.now().strftime('%d/%m/%Y')}"
        
        # Costruisci il report HTML
        stats_html = ""
        for user, stats in report_data.items():
            stats_html += f"""
            <div style="margin-bottom: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 5px;">
                <h3>{user}</h3>
                <ul>
            """
            for sensor, values in stats.items():
                stats_html += f"""
                    <li><strong>{self.get_sensor_name(sensor)}:</strong> 
                        Media: {values['mean']:.2f}, 
                        Min: {values['min']:.2f}, 
                        Max: {values['max']:.2f}
                    </li>
                """
            stats_html += """
                </ul>
            </div>
            """
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="padding: 20px;">
                    <h2 style="color: #0066cc;">📊 Report Giornaliero Sistema di Monitoraggio</h2>
                    <p>Data: {datetime.now().strftime('%d/%m/%Y')}</p>
                    
                    <h3>Statistiche Utenti:</h3>
                    {stats_html}
                    
                    <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
                        Report automatico generato dal Sistema di Monitoraggio IoT
                    </p>
                </div>
            </body>
        </html>
        """
        
        text_body = f"Report Giornaliero - {datetime.now().strftime('%d/%m/%Y')}\n\n"
        for user, stats in report_data.items():
            text_body += f"\n{user}:\n"
            for sensor, values in stats.items():
                text_body += f"  - {self.get_sensor_name(sensor)}: Media={values['mean']:.2f}\n"
        
        try:
            self.send_email(recipient_email, subject, text_body, html_body)
            return True
        except Exception as e:
            print(f"Errore invio report: {e}")
            return False
    
    def send_email(self, recipient, subject, text_body, html_body=None):
        """Funzione base per inviare email"""
        
        msg = MIMEMultipart('alternative')
        msg['From'] = self.sender_email
        msg['To'] = recipient
        msg['Subject'] = subject
        
        # Aggiungi parti testo e HTML
        part1 = MIMEText(text_body, 'plain')
        msg.attach(part1)
        
        if html_body:
            part2 = MIMEText(html_body, 'html')
            msg.attach(part2)
        
        # Invia l'email
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
    
    @staticmethod
    def get_sensor_name(sensor_type):
        """Restituisce il nome leggibile del sensore"""
        sensor_names = {
            'acc': 'Accelerometro',
            'bvp': 'Volume Polso Sanguigno',
            'eda': 'Attività Elettrodermica',
            'hr': 'Frequenza Cardiaca',
            'ibi': 'Inter-Beat Interval',
            'temp': 'Temperatura Cutanea'
        }
        return sensor_names.get(sensor_type, sensor_type.upper())


# utils/anomaly_detector.py
import numpy as np
from collections import deque
from datetime import datetime, timedelta

class AnomalyDetector:
    def __init__(self, window_size=20, z_threshold=3):
        """
        Inizializza il rilevatore di anomalie
        
        Args:
            window_size: Dimensione della finestra per la media mobile
            z_threshold: Soglia Z-score per rilevare anomalie
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.data_windows = {}  # Dizionario per memorizzare le finestre per ogni sensore/utente
        
        # Soglie specifiche per sensore (valori normali)
        self.sensor_thresholds = {
            'hr': {'min': 40, 'max': 180},      # Frequenza cardiaca
            'temp': {'min': 35, 'max': 39},     # Temperatura corporea
            'eda': {'min': 0.01, 'max': 20},    # Attività elettrodermica
            'bvp': {'min': -100, 'max': 100},   # Blood volume pulse
            'ibi': {'min': 300, 'max': 2000},   # Inter-beat interval (ms)
            'acc': {'min': 0, 'max': 5}         # Accelerazione (g)
        }
    
    def add_value(self, user_id, sensor_type, value):
        """Aggiunge un valore e controlla se è un'anomalia"""
        
        key = f"{user_id}_{sensor_type}"
        
        # Inizializza la finestra se non esiste
        if key not in self.data_windows:
            self.data_windows[key] = deque(maxlen=self.window_size)
        
        window = self.data_windows[key]
        
        # Aggiungi il valore alla finestra
        window.append(value)
        
        # Controlla anomalie solo se abbiamo abbastanza dati
        if len(window) >= self.window_size // 2:
            return self.detect_anomaly(sensor_type, value, window)
        
        return None
    
    def detect_anomaly(self, sensor_type, current_value, window):
        """
        Rileva anomalie usando multiple tecniche
        
        Returns:
            dict con informazioni sull'anomalia o None
        """
        
        anomalies = []
        
        # 1. Controllo soglie assolute
        if sensor_type in self.sensor_thresholds:
            thresholds = self.sensor_thresholds[sensor_type]
            if current_value < thresholds['min'] or current_value > thresholds['max']:
                anomalies.append({
                    'type': 'absolute_threshold',
                    'message': f"Valore fuori range normale ({thresholds['min']}-{thresholds['max']})",
                    'severity': 'high'
                })
        
        # 2. Z-score (deviazione dalla media)
        if len(window) >= 3:
            mean = np.mean(window)
            std = np.std(window)
            
            if std > 0:
                z_score = abs((current_value - mean) / std)
                if z_score > self.z_threshold:
                    anomalies.append({
                        'type': 'statistical',
                        'message': f"Deviazione significativa dalla media (Z-score: {z_score:.2f})",
                        'severity': 'medium' if z_score < 4 else 'high',
                        'z_score': z_score,
                        'mean': mean,
                        'std': std
                    })
        
        # 3. Cambio rapido (confronto con valore precedente)
        if len(window) >= 2:
            prev_value = window[-2]
            change_rate = abs((current_value - prev_value) / prev_value * 100) if prev_value != 0 else 0
            
            # Soglie di cambio rapido per sensore
            rapid_change_thresholds = {
                'hr': 30,    # 30% di cambio
                'temp': 5,   # 5% di cambio
                'eda': 50,   # 50% di cambio
                'bvp': 40,   # 40% di cambio
                'ibi': 25,   # 25% di cambio
                'acc': 100   # 100% di cambio (movimento brusco)
            }
            
            threshold = rapid_change_thresholds.get(sensor_type, 50)
            if change_rate > threshold:
                anomalies.append({
                    'type': 'rapid_change',
                    'message': f"Cambio rapido rilevato ({change_rate:.1f}%)",
                    'severity': 'low' if change_rate < threshold * 2 else 'medium',
                    'change_rate': change_rate
                })
        
        # 4. Pattern anomalo (trend sostenuto)
        if len(window) >= 5:
            recent_values = list(window)[-5:]
            trend = self.detect_trend(recent_values)
            
            if trend:
                anomalies.append({
                    'type': 'trend',
                    'message': f"Trend {trend} sostenuto",
                    'severity': 'low',
                    'trend': trend
                })
        
        # Restituisci l'anomalia più grave se presente
        if anomalies:
            # Ordina per severità
            severity_order = {'high': 3, 'medium': 2, 'low': 1}
            anomalies.sort(key=lambda x: severity_order.get(x['severity'], 0), reverse=True)
            
            return {
                'timestamp': datetime.now(),
                'value': current_value,
                'anomalies': anomalies,
                'window_mean': float(np.mean(window)),
                'window_std': float(np.std(window))
            }
        
        return None
    
    def detect_trend(self, values):
        """Rileva trend crescente o decrescente"""
        if len(values) < 3:
            return None
        
        differences = [values[i+1] - values[i] for i in range(len(values)-1)]
        
        # Tutti positivi = trend crescente
        if all(d > 0 for d in differences):
            return "crescente"
        # Tutti negativi = trend decrescente
        elif all(d < 0 for d in differences):
            return "decrescente"
        
        return None
    
    def get_statistics(self, user_id, sensor_type):
        """Ottiene statistiche per un sensore specifico"""
        key = f"{user_id}_{sensor_type}"
        
        if key not in self.data_windows or len(self.data_windows[key]) == 0:
            return None
        
        window = self.data_windows[key]
        return {
            'mean': float(np.mean(window)),
            'std': float(np.std(window)),
            'min': float(np.min(window)),
            'max': float(np.max(window)),
            'median': float(np.median(window)),
            'count': len(window)
        }