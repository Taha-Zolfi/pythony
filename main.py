from quart import Quart, request, send_from_directory, render_template_string
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.auth import SendCodeRequest, SignInRequest
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import CodeSettings, InputPhoneContact
import os
import time
import pandas as pd
from werkzeug.utils import secure_filename

app = Quart(__name__)
port = 3000

# Your Telegram API credentials
API_ID = 23787541
API_HASH = "fc1f17f7d2e81b0ad904228f002c01c9"

client = None
phone_number = None
auth_code_hash = None
string_session = StringSession("")  # Create an empty string session to start with

# Set up the upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def load_phone_numbers(file_path):
    df = pd.read_excel(file_path)
    phone_numbers = df['موبایل'].astype(str).tolist()  # Ensure phone numbers are strings
    return phone_numbers

@app.route("/")
async def index():
    return await render_template_string('''
    <!DOCTYPE html>
    <html lang="fa">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>ورود شماره تلفن</title>
      <link rel="stylesheet" href="/public/styles.css">
    </head>
    <body>
      <div class="container">
        <h2>ورود شماره تلفن</h2>
        <form action="/sendCode" method="post">
          <label for="phoneNumber">شماره تلفن:</label>
          <input type="text" id="phoneNumber" name="phoneNumber" required><br><br>
          <input type="submit" value="ارسال کد">
        </form>
      </div>
    </body>
    </html>
    ''')

@app.route("/sendCode", methods=["POST"])
async def send_code():
    global client, phone_number, auth_code_hash
    phone_number = (await request.form)["phoneNumber"]

    client = TelegramClient(string_session, API_ID, API_HASH)
    await client.connect()
    
    try:
        result = await client(SendCodeRequest(phone_number, API_ID, API_HASH, CodeSettings()))
        auth_code_hash = result.phone_code_hash

        return await render_template_string('''
        <!DOCTYPE html>
        <html lang="fa">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>ورود کد احراز هویت</title>
          <link rel="stylesheet" href="/public/styles.css">
        </head>
        <body>
          <div class="container">
            <h2>ورود کد احراز هویت</h2>
            <form action="/authenticate" method="post">
              <label for="authCode">کد احراز هویت:</label>
              <input type="text" id="authCode" name="authCode" required><br><br>
              <input type="submit" value="ورود">
            </form>
          </div>
        </body>
        </html>
        ''')
    except Exception as e:
        print("Failed to send authentication code:", e)
        return "Failed to send authentication code.", 500

@app.route("/authenticate", methods=["POST"])
async def authenticate():
    global client, phone_number, auth_code_hash
    auth_code = (await request.form)["authCode"]

    try:
        await client(SignInRequest(phone_number, auth_code_hash, auth_code))

        return await render_template_string('''
        <!DOCTYPE html>
        <html lang="fa">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>ارسال پیام</title>
          <link rel="stylesheet" href="/public/styles.css">
        </head>
        <body>
          <div class="container">
            <h2>ارسال پیام</h2>
            <form action="/sendMessage" method="post" enctype="multipart/form-data">
              <label for="message">پیام:</label>
              <input type="text" id="message" name="message" required><br><br>
              <label for="imagePath">عکس:</label>
              <input type="file" id="imagePath" name="imagePath" accept="image/*"><br><br>
              <label for="filePath">فایل:</label>
              <input type="file" id="filePath" name="filePath"><br><br>
              <label for="excelFile">فایل اکسل:</label>
              <input type="file" id="excelFile" name="excelFile" accept=".xlsx" required><br><br>
              <input type="submit" value="ارسال">
            </form>
          </div>
        </body>
        </html>
        ''')
    except Exception as e:
        print("Failed to authenticate:", e)
        return "Failed to authenticate.", 500

@app.route("/sendMessage", methods=["POST"])
async def send_message():
    global client
    form = await request.form
    message = form["message"]
    image_file = (await request.files).get("imagePath")
    file_file = (await request.files).get("filePath")
    excel_file = (await request.files).get("excelFile")

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_file.filename)) if image_file else None
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file_file.filename)) if file_file else None
    excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))

    if image_path:
        await image_file.save(image_path)
    if file_path:
        await file_file.save(file_path)
    await excel_file.save(excel_path)

    target_phone_numbers = load_phone_numbers(excel_path)
    logs = ""

    try:
        for i, phone in enumerate(target_phone_numbers):
            contact = InputPhoneContact(client_id=i, phone=phone, first_name=f"User{i}", last_name="")
            result = await client(ImportContactsRequest([contact]))

            if result.imported:
                user = result.imported[0]

                try:
                    if image_path:
                        file = await client.upload_file(image_path)
                        await client.send_file(user.user_id, file, caption=message)
                        log = f"عکس با متن برای {user.user_id} ارسال شد"
                    elif file_path:
                        await client.send_file(user.user_id, file_path, caption=message, force_document=True)
                        log = f"فایل با متن برای {user.user_id} ارسال شد"
                    else:
                        await client.send_message(user.user_id, message)
                        log = f"متن برای {user.user_id} ارسال شد"
                    logs += f"{log}\n"
                    print(log)
                except Exception as e:
                    log = f"ارسال فایل به {user.user_id} با شکست مواجه شد: {e}"
                    logs += f"{log}\n"
                    print(log)
            else:
                log = f"وارد کردن مخاطب {phone} با شکست مواجه شد"
                logs += f"{log}\n"
                print(log)

            time.sleep(3)

        if image_path:
            os.remove(image_path)
        if file_path:
            os.remove(file_path)
        os.remove(excel_path)

        return await render_template_string(f'''
        <!DOCTYPE html>
        <html lang="fa">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>نتایج ارسال</title>
          <link rel="stylesheet" href="/public/styles.css">
        </head>
        <body>
          <div class="container">
            <h2>نتایج ارسال</h2>
            <pre>{logs}</pre>
          </div>
        </body>
        </html>
        ''')
    except Exception as e:
        print("Failed to send messages:", e)
        return "Failed to send messages.", 500

@app.route('/public/<path:filename>')
async def serve_static_files(filename):
    return await send_from_directory('public', filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
