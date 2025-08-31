import os
import time
import argparse
import requests
import pandas as pd

SERVER_URL = "http://127.0.0.1:5000/api/data"  # cambiare con URL cloud quando serve

def send_data(username, data_folder, speed):
    sensors = [
        "wrist_acc",
        "wrist_bvp",
        "wrist_eda",
        "wrist_hr",
        "wrist_ibi",
        "wrist_skin_temperature"
    ]

    for sensor in sensors:
        file_path = os.path.join(data_folder, sensor + ".csv")
        if not os.path.exists(file_path):
            print(f"⚠️ Nessun file trovato per {sensor}")
            continue

        print(f"📂 Lettura da {file_path}...")
        df = pd.read_csv(file_path)

        for _, row in df.iterrows():
            if sensor == "wrist_acc":
                for axis in ["X", "Y", "Z"]:
                    try:
                        value = float(row[axis])
                    except Exception:
                        continue
                    payload = {
                        "username": username,
                        "sensor_type": f"{sensor}_{axis}",
                        "value": value
                    }
                    send_payload(payload, speed)
            else:
                try:
                    value = float(row["value"])
                except Exception:
                    continue
                payload = {
                    "username": username,
                    "sensor_type": sensor,
                    "value": value
                }
                send_payload(payload, speed)

def send_payload(payload, speed):
    try:
        r = requests.post(SERVER_URL, json=payload)
        if r.status_code == 200:
            print(f"✅ Inviato: {payload}")
        else:
            print(f"❌ Errore {r.status_code}: {r.text}")
    except Exception as e:
        print(f"🚨 Errore invio dati: {e}")
    time.sleep(1 / speed)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True, help="Username del proprietario dei dati")
    parser.add_argument("--data-folder", required=True, help="Cartella con i file CSV")
    parser.add_argument("--speed", type=float, default=1, help="Velocità invio dati (righe al secondo)")
    args = parser.parse_args()

    send_data(args.username, args.data_folder, args.speed)
