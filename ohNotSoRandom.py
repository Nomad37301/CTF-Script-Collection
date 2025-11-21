import asyncio
import websockets
import json
from randcrack import RandCrack

# --- konfig ---
URI = "ws://217.216.111.220:3080/ws" 
N = 1_000_000   
TARGET = 10000  
BITS = 32       
COUNT = 624     

async def solve_challenge():
    """
    Menjalankan 3 fase serangan:
    1. Mengumpulkan 624 output randbits.
    2. Meng-kloning state RNG server.
    3. Memprediksi dan mengirim 10000 tebakan yang benar.
    """
    
    print(f"Menghubungi server di {URI}...")
    
    async with websockets.connect(URI) as ws:
        rc = RandCrack()
        
        # --- phase 1: recive the dataaaaaaaaaaaaaaaaaaaaaaaaaaa ---
        print(f"phase 1: Mengumpulkan {COUNT} output 'randbits'...")
        
        for i in range(COUNT):
            guess_payload = {"type": "guess", "number": 1}
            await ws.send(json.dumps(guess_payload))
            
            response_str = await ws.recv()
            data = json.loads(response_str)
            
            if data.get("type") == "guess_result":
                randbits = data.get("guess_id")
                rc.submit(randbits)
                print(f"Mengumpulkan bits... {i+1}/{COUNT}", end='\r')
            else:
                print(f"\nError: Respons tidak terduga saat pengumpulan: {data}")
                return

        print(f"\nSukses! {COUNT} output telah dikumpulkan. RNG server telah dikloning.")
        
        # --- phase 3: Predict ---
        print("phase 3: start prediksi dan mengirim 10,000 tebakan...")
        
        for i in range(TARGET):
            # 1. prediksi 'randbits' dan hitung tebakan yang benar
            predicted_bits = rc.predict_getrandbits(BITS)
            correct_guess = (predicted_bits % N) + 1
            
            # 2. kirim tebakan yang sudah pasti benar ast yatuhan astaga
            attack_payload = {"type": "guess", "number": correct_guess}
            await ws.send(json.dumps(attack_payload))
            
            # 3. respons hasil tebakan
            response_str = await ws.recv()
            data = json.loads(response_str)

            # 4. apakah tebakan kita benar?
            if data.get("type") == "guess_result" and data.get("result") == "correct":
                current_score = data.get("score")
                print(f"  [+] Tebakan {i+1}/{TARGET} benar! (Skor: {current_score})", end='\r')
                
                # 5. PERIKSA APAKAH INI TEBAKAN TERAKHIR
                if current_score == TARGET:
                    print("\n[*] Target skor tercapai! Menunggu pesan flag...")
                    # JANGAN LAKUKAN LOOP LAGI. TUNGGU FLAG.
                    flag_response_str = await ws.recv() # Menunggu pesan kedua
                    flag_data = json.loads(flag_response_str)
                    
                    if flag_data.get("type") == "flag":
                        print("\n\n" + "="*50)
                        print(f"FLAG DITEMUKAN! YIPPPIIEEEE JANCOOKKKKKKK")
                        print(f"Flag: {flag_data.get('flag')}")
                        print("="*50)
                        return # selesai
                    else:
                        print(f"\nMenerima {flag_data.get('type')} padahal mengharapkan flag.")
                        return

            # Ini adalah 'safety check' jika kita kehilangan sinkronisasi
            elif data.get("type") == "guess_result" and data.get("result") == "incorrect":
                print(f"\nGAGAL! Sinkronisasi RNG hilang pada tebakan {i+1}.")
                print(f"Server mengharapkan : {data.get('number')}")
                print(f"Kita menebak        : {correct_guess}")
                return
            else:
                print(f"\nMenerima pesan yang tidak terduga: {data}")
                return
            
        print(f"\nLoop selesai tetapi flag tidak diterima. Ini seharusnya tidak terjadi.")

if __name__ == "__main__":
    asyncio.run(solve_challenge())