from pyngrok import ngrok
import subprocess

# 1. Streamlit portunu belirle
port = 8501

# 2. Ngrok HTTP tüneli başlat
public_url = ngrok.connect(port)
print(f"Site internetten erişilebilir: {public_url}")

# 3. Streamlit'i başlat
subprocess.run(["streamlit", "run", "app.py", "--server.port", str(port)])
