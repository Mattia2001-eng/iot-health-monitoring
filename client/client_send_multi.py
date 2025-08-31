import os
import time
import argparse
import requests
import pandas as pd

SERVER_URL = "http://127.0.0.1:5000/api/data"  # URL server

SENSOR_FILES = {
    "wrist_acc": ["ax", "ay", "az"],
    "wrist_bvp": ["bvp"],
    "wrist_eda": ["eda"],
    "wrist_hr": ["hr"],
    "wrist_ibi": ["ibi"],
    "wrist_skin_temperature": ["temp"]
}

def send_user_data(username, folder, speed):
    print(f"\n📦 Invio dati per utente: {username}")
    
    for sensor, columns in SENSOR_FILES.items():
        file_path = os.path.join(folder, f"{sensor}.csv")
        if not os.path.exists(file_path):
            print(f"⚠️ File non trovato: {file_path}")
            continue

        df = pd.read_csv(file_path)
        print(f"📂 Lettura {file_path}...")

        for _, row in df.iterrows():
            if sensor == "wrist_acc":
                value = float(row[["ax", "ay", "az"]].mean())
            else:
                # Usa la prima colonna dopo timestamp
                col = df.columns[1]  # timestamp + valore specifico
                value = float(row[col])

            payload = {
                "username": username,
                "sensor_type": sensor,
                "value": value
            }

            try:
                r = requests.post(SERVER_URL, json=payload)
                if r.status_code == 200:
                    print(f"✅ {sensor}: {value}")
                else:
                    print(f"❌ {r.status_code}: {r.text}")
            except Exception as e:
                print(f"🚨 Errore invio dati: {e}")

            time.sleep(1 / speed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=float, default=1, help="righe al secondo")
    parser.add_argument("--users", nargs="+", required=True,
                        help="Lista utenti nel formato user:folder_dataset")
    args = parser.parse_args()

    for user_pair in args.users:
        if ":" not in user_pair:
            print(f"⚠️ Formato errato: {user_pair}, deve essere username:folder")
            continue
        username, folder = user_pair.split(":", 1)
        if not os.path.exists(folder):
            print(f"⚠️ Cartella non trovata: {folder}")
            continue
        send_user_data(username, folder, args.speed)
