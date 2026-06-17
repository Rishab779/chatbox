# 💬 Realtime Cloud Chatbox

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg)
![AWS](https://img.shields.io/badge/AWS-EC2%20%7C%20S3%20%7C%20DynamoDB-FF9900.svg)
![Groq](https://img.shields.io/badge/AI-Groq%20Llama%203-black.svg)

A production-ready, full-stack real-time chat application powered by Python, AWS, and AI. Built with a blazing fast **FastAPI** backend and an interactive **Streamlit** frontend.

## ✨ Features

- **Real-Time Messaging:** Instantaneous communication using WebSockets.
- **Secure Authentication:** Gmail-based OTP verification for new registrations with bcrypt password hashing.
- **Cloud Database:** Persistent chat history and user data isolated by registration date using **AWS DynamoDB**.
- **Media & File Sharing:** Upload profile pictures, images, and PDFs securely to **AWS S3**.
- **AI Document Summarization:** Instantly generate intelligent summaries of uploaded PDFs directly in the chat using the **Groq API (Llama 3)**.
- **Always Online:** Ready to be deployed on an AWS EC2 instance using PM2 for 24/7 uptime.

---

## 🏗️ Architecture & Tech Stack

- **Frontend:** Streamlit
- **Backend:** FastAPI, Uvicorn, WebSockets
- **Database:** Amazon DynamoDB
- **Storage:** Amazon S3
- **Deployment:** AWS EC2 (Ubuntu), PM2
- **AI Integration:** Groq API (`llama-3.1-8b-instant`)

---

## 🛠️ Setup Instructions (Localhost)

Follow these instructions to run the application on your own machine (Mac or Windows).

### 1. Prerequisites
- Python 3.10 or higher installed.
- An AWS account (with an S3 bucket and DynamoDB access).
- A [Groq API Key](https://console.groq.com/) (free tier works perfectly).
- A Gmail account with an App Password (for sending OTPs).

### 2. Clone the Repository
```bash
git clone https://github.com/Rishab779/chatbox.git
cd chatbox
```

### 3. Create a Virtual Environment

**For macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**For Windows (Command Prompt / PowerShell):**
```cmd
python -m venv venv
venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Environment Variables
Create a file named `.env` in the root folder of the project and fill in your credentials. You can use `.env.example` as a template:

```env
# Email Setup
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password

# AWS Setup
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=ap-south-1
S3_BUCKET_NAME=your-s3-bucket-name

# Networking
CHATBOX_API_BASE=http://127.0.0.1:8000
CHATBOX_WS_BASE=ws://127.0.0.1:8000

# AI Configuration
GROQ_API_KEY=your_groq_api_key
DEFAULT_GROQ_MODEL=llama-3.1-8b-instant
```

---

## 🚀 Running on Localhost

You will need to open **two separate terminal windows** (ensure your virtual environment is activated in both).

**Terminal 1 (Start the Backend):**
```bash
uvicorn server.main:app --reload
```

**Terminal 2 (Start the Frontend):**
```bash
streamlit run client/app.py
```

Streamlit will automatically open a browser window at `http://localhost:8501`. 

---

## ☁️ Running on AWS EC2 (Production Deployment)

To deploy this application to the cloud so it runs 24/7 without needing your laptop open, we use an AWS EC2 instance running Ubuntu and `pm2`.

### 1. Connect to your EC2 instance
```bash
ssh -i /path/to/your/key.pem ubuntu@YOUR_EC2_IP
```

### 2. Install PM2 (If not already installed)
```bash
sudo apt update
sudo apt install npm
sudo npm install -g pm2
```

### 3. Clone and Setup
```bash
git clone https://github.com/Rishab779/chatbox.git
cd chatbox
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
*(Don't forget to create your `.env` file on the server using `nano .env`)*

### 4. Start the Application with PM2
We use PM2 to keep the processes alive in the background:

```bash
# Start FastAPI backend
pm2 start "venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000" --name chat-backend

# Start Streamlit frontend
pm2 start "venv/bin/streamlit run client/app.py" --name chat-frontend

# Save the PM2 list so it restarts on server reboot
pm2 save
```

### 5. Access your Live Chatbox
Open your browser and navigate to:
`http://YOUR_EC2_IP:8501`

*(Ensure you have opened port 8501 in your EC2 Security Group inbound rules!)*

---
*Built with ❤️ for real-time cloud communication.*
