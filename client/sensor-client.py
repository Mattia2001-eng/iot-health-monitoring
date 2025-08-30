import pandas as pd
import requests
import time
import json
import os
import sys
from datetime import datetime
import argparse
from pathlib import Path

class SensorClient:
    def __init__(self, server_url, client_id, data_folder, speed_multiplier=1):
        """
        Client per l'invio dei dati dei sensori dal dataset FatigueSet
        
        Args:
            server_url: URL del server (es. http://localhost:5000)
            client_id: ID univoco del client (es. username_device1)
            data_folder: Percorso alla cartella con i file CSV
            speed_multiplier: Moltiplicatore velocità invio (1=real-time, 60=1min diventa 1sec)
        """
        self.server_url = server_url.rstrip('/')
        self.client_id = client_id
        self.data_folder = Path(data_folder)
        self.speed_multiplier = speed_multiplier
        
        # Mapping dei file ai tipi di sensore con le colonne corrette
        self.sensor_configs = {
            'acc': {
                'file': 'wrist_acc.csv',
                'columns': ['timestamp', 'ax', 'ay', 'az'],
                'frequency': 32  # Hz dal dataset
            },
            'bvp': {
                'file': 'wrist_bvp.csv', 
                'columns': ['timestamp', 'bvp'],
                'frequency': 64  # Hz dal dataset
            },
            'eda': {
                'file': 'wrist_eda.csv',
                'columns': ['timestamp', 'eda'],
                'frequency': 4   # Hz dal dataset
            },
            'hr': {
                'file': 'wrist_hr.csv',
                'columns': ['timestamp', 'hr'],
                'frequency': 1   # Hz dal dataset
            },
            'ibi': {
                'file': 'wrist_ibi.csv',
                'columns': ['timestamp', 'duration'],
                'frequency': 1   # Variabile, ma approssimato
            },
            'temp': {
                'file': 'wrist_skin_temperature.csv',
                'columns': ['timestamp', 'temp'],
                'frequency': 4   # Hz dal dataset
            }
        }
        
        self.data_readers = {}
        self.current_indices = {}
        self.last_sent_time = {}
        self.load_data()
    
    def load_data(self):
        """Carica tutti i file CSV disponibili"""
        print(f"\n[{self.client_id}] 🔄 Caricamento dati da {self.data_folder}")
        print("="*60)
        
        for sensor_type, config in self.sensor_configs.items():
            filepath = self.data_folder / config['file']
            
            if filepath.exists():
                try:
                    # Leggi il CSV
                    df = pd.read_csv(filepath)
                    
                    # Verifica che le colonne esistano
                    expected_cols = config['columns']
                    if not all(col in df.columns for col in expected_cols):
                        print(f"  ⚠️  {config['file']}: Colonne non corrispondenti")
                        print(f"      Attese: {expected_cols}")
                        print(f"      Trovate: {list(df.columns)}")
                        continue
                    
                    # Converti timestamp UNIX in datetime
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                    
                    # Ordina per timestamp
                    df = df.sort_values('timestamp')
                    
                    self.data_readers[sensor_type] = df
                    self.current_indices[sensor_type] = 0
                    self.last_sent_time[sensor_type] = time.time()
                    
                    print(f"  ✅ {config['file']:30s} {len(df):6d} righe | Freq: {config['frequency']}Hz")
                    
                    # Mostra range temporale
                    if len(df) > 0:
                        start_time = df['datetime'].iloc[0].strftime('%H:%M:%S')
                        end_time = df['datetime'].iloc[-1].strftime('%H:%M:%S')
                        duration = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]) / 60
                        print(f"      Range: {start_time} - {end_time} ({duration:.1f} minuti)")
                    
                except Exception as e:
                    print(f"  ❌ Errore caricamento {config['file']}: {e}")
            else:
                print(f"  ⏭️  {config['file']} non trovato")
        
        print("="*60)
        print(f"✅ Caricati {len(self.data_readers)} sensori su {len(self.sensor_configs)}")
    
    def parse_sensor_value(self, sensor_type, row):
        """
        Estrae il valore appropriato dalla riga del CSV
        """
        data = {'timestamp': int(row['timestamp'])}
        
        if sensor_type == 'acc':
            # Accelerometro ha 3 assi
            data.update({
                'x': float(row['ax']),
                'y': float(row['ay']),
                'z': float(row['az']),
                'value': (row['ax']**2 + row['ay']**2 + row['az']**2)**0.5  # magnitude
            })
        
        elif sensor_type == 'bvp':
            data['value'] = float(row['bvp'])
        
        elif sensor_type == 'eda':
            data['value'] = float(row['eda'])
        
        elif sensor_type == 'hr':
            data['value'] = float(row['hr'])
        
        elif sensor_type == 'ibi':
            # IBI usa 'duration' invece di un valore diretto
            data['value'] = float(row['duration'])
        
        elif sensor_type == 'temp':
            data['value'] = float(row['temp'])
        
        return data
    
    def send_data(self, sensor_type, data):
        """Invia i dati al server"""
        url = f"{self.server_url}/sensors/{self.client_id}/{sensor_type}"
        
        try:
            response = requests.post(url, json=data, timeout=5)
            
            if response.status_code == 200:
                return True
            else:
                print(f"  ⚠️  Errore invio {sensor_type}: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Server non raggiungibile. Assicurati che il server sia attivo su {self.server_url}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Errore connessione per {sensor_type}: {e}")
            return False
    
    def run_synchronized(self):
        """
        Esegue l'invio sincronizzato basato sui timestamp reali
        """
        print(f"\n🚀 [{self.client_id}] Avvio invio sincronizzato al server {self.server_url}")
        print(f"⚡ Velocità: {self.speed_multiplier}x")
        print("📊 Premi Ctrl+C per fermare\n")
        
        if not self.data_readers:
            print("❌ Nessun dato da inviare!")
            return
        
        # Trova il timestamp minimo e massimo tra tutti i sensori
        all_timestamps = []
        for sensor_type, df in self.data_readers.items():
            if len(df) > 0:
                all_timestamps.extend(df['timestamp'].values)
        
        if not all_timestamps:
            print("❌ Nessun timestamp trovato nei dati!")
            return
        
        min_timestamp = min(all_timestamps)
        max_timestamp = max(all_timestamps)
        
        # Tempo di simulazione
        current_timestamp = min_timestamp
        start_real_time = time.time()
        
        print(f"📅 Simulazione dal timestamp {min_timestamp} al {max_timestamp}")
        print(f"⏱️  Durata simulazione: {(max_timestamp - min_timestamp) / self.speed_multiplier:.1f} secondi\n")
        
        try:
            sent_counts = {sensor: 0 for sensor in self.data_readers.keys()}
            last_print_time = time.time()
            
            while current_timestamp <= max_timestamp:
                data_sent_this_round = False
                
                # Per ogni sensore, invia i dati che hanno timestamp <= current_timestamp
                for sensor_type, df in self.data_readers.items():
                    idx = self.current_indices[sensor_type]
                    
                    # Invia tutti i dati fino al timestamp corrente
                    while idx < len(df) and df.iloc[idx]['timestamp'] <= current_timestamp:
                        row = df.iloc[idx]
                        sensor_data = self.parse_sensor_value(sensor_type, row)
                        
                        if self.send_data(sensor_type, sensor_data):
                            sent_counts[sensor_type] += 1
                            data_sent_this_round = True
                            
                            # Stampa solo alcuni messaggi per non intasare il terminale
                            if sensor_type == 'hr':  # Stampa solo per HR che ha frequenza bassa
                                dt = datetime.fromtimestamp(row['timestamp'])
                                print(f"  💓 [{dt.strftime('%H:%M:%S')}] HR: {sensor_data['value']:.1f} bpm")
                        
                        self.current_indices[sensor_type] = idx + 1
                        idx += 1
                
                # Stampa statistiche ogni 5 secondi
                if time.time() - last_print_time > 5:
                    print(f"\n📊 Progresso: {sent_counts}")
                    progress = (current_timestamp - min_timestamp) / (max_timestamp - min_timestamp) * 100
                    print(f"⏳ Completamento: {progress:.1f}%\n")
                    last_print_time = time.time()
                
                # Avanza nel tempo
                elapsed_real_time = time.time() - start_real_time
                current_timestamp = min_timestamp + (elapsed_real_time * self.speed_multiplier)
                
                # Piccola pausa per non sovraccaricare
                time.sleep(0.01)
                
                # Controlla se abbiamo finito tutti i dati
                all_done = all(
                    self.current_indices[sensor] >= len(df) 
                    for sensor, df in self.data_readers.items()
                )
                if all_done:
                    print("\n✅ Tutti i dati sono stati inviati!")
                    break
                
        except KeyboardInterrupt:
            print(f"\n⛔ [{self.client_id}] Interruzione manuale")
        except Exception as e:
            print(f"\n❌ [{self.client_id}] Errore: {e}")
        finally:
            self.print_summary(sent_counts)
    
    def print_summary(self, sent_counts):
        """Stampa un riepilogo dell'invio"""
        print(f"\n{'='*60}")
        print(f"📊 [{self.client_id}] RIEPILOGO INVIO")
        print(f"{'='*60}")
        
        for sensor_type, df in self.data_readers.items():
            sent = sent_counts.get(sensor_type, 0)
            total = len(df)
            percentage = (sent / total * 100) if total > 0 else 0
            
            status = "✅" if percentage == 100 else "⏳"
            print(f"  {status} {sensor_type:5s}: {sent:6d}/{total:6d} righe ({percentage:5.1f}%)")
        
        total_sent = sum(sent_counts.values())
        total_rows = sum(len(df) for df in self.data_readers.values())
        total_percentage = (total_sent / total_rows * 100) if total_rows > 0 else 0
        
        print(f"{'='*60}")
        print(f"  📈 TOTALE: {total_sent}/{total_rows} ({total_percentage:.1f}%)")

def main():
    parser = argparse.ArgumentParser(
        description='Client per invio dati sensori IoT dal dataset FatigueSet',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  python sensor_client.py --client-id mario_device1 --data-folder ./data/fatigueset
  python sensor_client.py --client-id test --data-folder ./data --speed 60 --server http://localhost:5000
        """
    )
    
    parser.add_argument('--server', 
                      default='http://localhost:5000', 
                      help='URL del server (default: http://localhost:5000)')
    
    parser.add_argument('--client-id', 
                      required=True,
                      help='ID univoco del client (es: mario_device1)')
    
    parser.add_argument('--data-folder', 
                      required=True,
                      help='Percorso alla cartella con i file CSV del dataset')
    
    parser.add_argument('--speed', 
                      type=float, 
                      default=60.0,
                      help='Moltiplicatore velocità (60=1 minuto diventa 1 secondo)')
    
    args = parser.parse_args()
    
    # Verifica che la cartella esista
    if not os.path.exists(args.data_folder):
        print(f"❌ Errore: La cartella {args.data_folder} non esiste!")
        print("Assicurati di aver scaricato il dataset FatigueSet")
        sys.exit(1)
    
    # Crea e avvia il client
    print(f"\n{'='*60}")
    print(f"🏥 HEALTH MONITOR IoT CLIENT")
    print(f"{'='*60}")
    
    client = SensorClient(
        server_url=args.server,
        client_id=args.client_id,
        data_folder=args.data_folder,
        speed_multiplier=args.speed
    )
    
    client.run_synchronized()

if __name__ == '__main__':
    main()