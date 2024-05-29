from flask import Flask,redirect,url_for,request,render_template,flash,session, jsonify
import boto3
import mysql.connector
from datetime import datetime
import openai, requests, uuid, time, json
from key import secret_key,salt
from itsdangerous import URLSafeTimedSerializer
from stoken import token
from cmail import sendmail

app = Flask(__name__)
app.secret_key=secret_key
app.config['SESSION_TYPE']='filesystem'

comprehend = boto3.client('comprehend')
transcribe = boto3.client('transcribe')
textract = boto3.client('textract')
openai.api_key = '#'

mydb = mysql.connector.connect(host='localhost', user='root', password='$', db='#')
cursor = mydb.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username varchar(20) PRIMARY KEY,
        email varchar(30) not null unique,
        password varchar(20)
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    text_input VARCHAR(500),
    sentiment VARCHAR(20),
    sdate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    username VARCHAR(20) REFERENCES users(username)
)
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS chatbot (
    id INT AUTO_INCREMENT PRIMARY KEY,
    text_input VARCHAR(500),
    response VARCHAR(10000),
    sdate date,
    username VARCHAR(20) REFERENCES users(username)
)
""")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if session.get('user'):
        return redirect(url_for('home'))
    if request.method=='POST':
        username=request.form['username']
        password=request.form['password']
        cursor=mydb.cursor(buffered=True)
        cursor.execute('select count(*) from users where username=%s and password=%s',[username,password])
        count=cursor.fetchone()[0]
        if count==1:
            session['user']=username
            return redirect(url_for('home'))    
        else:
            flash('Invalid username or password')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/registration',methods=['GET','POST'])
def registration():
    if request.method=='POST':
        username=request.form['username']
        password=request.form['password']
        email=request.form['email']
        cursor=mydb.cursor(buffered=True)
        cursor.execute('select count(*) from users where username=%s',[username])
        count=cursor.fetchone()[0]
        cursor.execute('select count(*) from users where email=%s',[email])
        count1=cursor.fetchone()[0]
        cursor.close()
        if count==1:
            flash('Username is already in use')
            return render_template('registration.html')
        elif count1==1:
            flash('Email already in use')
            return render_template('registration.html')
        data={'username':username,'password':password,'email':email}
        subject='Email Confirmation'
        body=f"Welcome to our AWS-Powered NLP Application {username}!!!\n\nThanks for registering on our application....\nClick on the below link to confirm your registration: \n\n {url_for('confirm',token=token(data),_external=True)}\n\nWith Regards,\nAWS-NLP Team"
        sendmail(to=email,subject=subject,body=body)
        flash('Confirmation link sent to mail')
        return redirect(url_for('registration'))
    return render_template('registration.html')

@app.route('/confirm/<token>')
def confirm(token):
    try:
        serializer=URLSafeTimedSerializer(secret_key)
        data=serializer.loads(token,salt=salt,max_age=180)
    except Exception:
        flash('Link expired register again')
        return redirect(url_for('registration'))
    else:
        cursor=mydb.cursor(buffered=True)
        username=data['username']
        cursor.execute('select count(*) from users where username=%s',[username])
        count=cursor.fetchone()[0]
        if count==1:
            cursor.close()
            flash('You are already registerterd!')
            return redirect(url_for('login'))
        else:
            cursor.execute('insert into users values(%s,%s,%s)',[data['username'],data['email'],data['password']])
            mydb.commit()
            cursor.close()
            flash('Details registered!')
            return redirect(url_for('login'))
        
@app.route('/forgotpassword', methods=["GET","POST"])
def forgotpassword():
    if request.method=='POST':
        username=request.form['username']
        password=request.form['password']
        confirmPassword = request.form['password1']
        if password != confirmPassword:
            flash('Both passwords are not same')
            return redirect(url_for('forgotpassword'))
        cursor=mydb.cursor(buffered=True)
        cursor.execute('select email from users where username=%s',[username])
        email = cursor.fetchone()[0]
        cursor.close()
        data={'username':username,'password':password, 'email':email}
        subject='Forgot Password Confirmation'
        body=f"Welcome to our Calorie Counter Application {username}!!!\n\nThis is your account's password reset confirmation email....\nClick on this link to confirm your reset password - \n\n{url_for('reset',token=token(data),_external=True)}\n\nIf you have not initiated to change the password, please ignore this mail, someone mistakenly entered your username.\n\nWith Regards,\nCalorie Counter Team"
        sendmail(to=email,subject=subject,body=body)
        flash('Confirmation link sent to mail')
        return redirect(url_for('forgotpassword'))
    return render_template('forgotpassword.html')

@app.route('/reset/<token>')
def reset(token):
    try:
        serializer=URLSafeTimedSerializer(secret_key)
        data=serializer.loads(token,salt=salt,max_age=180)
    except Exception:
        flash('Link expired reset your password again')
        return redirect(url_for('forgotpassword'))
    else:
        cursor=mydb.cursor(buffered=True)
        username=data['username']
        password = data['password']
        cursor=mydb.cursor(buffered=True)
        cursor.execute('update users set password = %s where username = %s',[password, username])
        mydb.commit()
        cursor.close()
        flash('Password Reset Successful!')
        return redirect(url_for('login'))
    
@app.route('/home')
def home():
    if session.get('user'):
        return render_template('home.html')
    else:
        return redirect(url_for('login'))

def sentiment_analysis(text):
     response = comprehend.detect_sentiment(Text=text, LanguageCode='en')
     response=response['Sentiment']
     date = datetime.now().date();
     cursor=mydb.cursor(buffered=True)
     username=session.get('user')
     cursor.execute('insert into sentiment_analysis (text_input, sentiment, username, sdate) values (%s,%s,%s, %s)', [text, response, username, date])
     mydb.commit()
     return response

@app.route('/sentiment', methods=["GET","POST"])
def sentiment():
    if session.get('user'):
        if request.method=='POST':
            text = request.form['text']
            response = sentiment_analysis(text)
            flash(f'The sentiment analysis of "{text}" is "{response}"')
            return redirect(url_for('sentiment'))
        else:
            return render_template('sentiment.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/textToSpeech', methods=["GET","POST"])
def textToSpeech():
    if session.get('user'):
        return render_template('textToSpeech.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/logout')
def logout():
    if session.get('user'):
        session.pop('user')
        flash('You are successfully logged out')
        return redirect(url_for('login'))
    else:
        return redirect(url_for('login'))
    
def transcribe_audio(audio_file_uri):
    transcribe_client = boto3.client('transcribe')
    unique_id = uuid.uuid4()
    job_name = f'speech-to-text-job-{unique_id}'
    response = transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode='en-US',
        MediaFormat='wav',
        Media={'MediaFileUri': audio_file_uri}
    )
    while True:
        result = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        status = result['TranscriptionJob']['TranscriptionJobStatus']
        if status in ['COMPLETED', 'FAILED']:
            break
        print(f'Waiting for transcription to complete. Current status: {status}')
        time.sleep(5) 
    if status == 'COMPLETED':
        transcription_uri = result['TranscriptionJob']['Transcript']['TranscriptFileUri']
        return transcription_uri  
    else:
        raise Exception('Transcription job failed or was not completed successfully.')
		
@app.route('/speechToText', methods=["GET","POST"])
def speechToText():
    if session.get('user'):
        if request.method=='POST':
            try:
                if 'audioFile' not in request.files:
                    return jsonify({'error': 'No audio file provided'}), 400
                audio_file = request.files['audioFile']
                bucket_name = '#'
                s3_client = boto3.client('s3')
                s3_client.upload_fileobj(audio_file, bucket_name, audio_file.filename)
                audio_file_uri = f's3://{bucket_name}/{audio_file.filename}'
                transcription = transcribe_audio(audio_file_uri)
                if transcription:
                    response = requests.get(transcription)
                    if response.status_code == 200:
                        transcription_data = json.loads(response.text)
                        result = transcription_data['results']['transcripts'][0]['transcript']
                        response = sentiment_analysis(result)
                        flash(f'The transcript of the audio is "{result}"\n'
                              f'\n\nThe sentiment analysis of this transcript is "{response}"')
                    else:
                        print("Failed to retrieve transcription.")
                    return jsonify({'transcription': transcription}), 200
                else:
                    return jsonify({'error': 'Speech-to-text conversion failed'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 400
        else:
            return render_template('speechToText.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/imagetext', methods=["GET","POST"])
def imagetext():
    if session.get('user'):
        if request.method == 'POST' and 'image' in request.files:
            image_file = request.files['image']
            if image_file.filename == '':
                flash('No image selected')
                return redirect(url_for('imagetext'))
            image_content = image_file.read()
            response = textract.detect_document_text(Document={'Bytes': image_content})
            extracted_text = ''
            for item in response['Blocks']:
                if item['BlockType'] == 'LINE':
                    extracted_text += item['Text'] + '\n'
            response = sentiment_analysis(extracted_text)
            flash(f'The text present in the image is "{extracted_text}".\n'
                  f'The sentiment analysis of that text is "{response}".')
            return redirect(url_for('imagetext'))
        else:
            return render_template('imagetext.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/chatbot', methods=["GET","POST"])
def chatbot():
    if session.get('user'):
        if request.method == 'POST':
            try:
                user_input = request.form['text']
                response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo", 
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": f"{user_input}"},
                        ]
                    )
                chat_response = response['choices'][0]['message']['content']
                date = datetime.now().date()
                cursor=mydb.cursor(buffered=True)
                print(user_input, chat_response)
                username=session.get('user')
                cursor.execute('insert into chatbot (text_input, response, username, sdate) values (%s,%s,%s, %s)', [user_input, chat_response, username, date])
                mydb.commit()
                cursor.execute('select * from chatbot where username = %s and sdate = %s order by id',[username, date])
                data=cursor.fetchall()
                cursor.close()
                return render_template('chatbot.html', data=data)
            except:
                username=session.get('user')
                cursor=mydb.cursor(buffered=True)
                date = datetime.now().date()
                cursor.execute('select * from chatbot where username = %s and sdate = %s order by id asc',[username, date])
                data=cursor.fetchall()
                cursor.close()
                return render_template('chatbot.html',data=data)
        else:
            username=session.get('user')
            cursor=mydb.cursor(buffered=True)
            date = datetime.now().date()
            cursor.execute('select * from chatbot where username = %s and sdate = %s order by id asc',[username, date])
            data=cursor.fetchall()
            cursor.close()
            return render_template('chatbot.html', data = data)
    else:
        return redirect(url_for('login'))
    
@app.route('/history', methods=["GET","POST"])
def history():
    if session.get('user'):
        if request.method == 'POST':
            date = request.form.get('selected_date')
            query_type = request.form.get('query_type')
            if date and query_type:
                username = session.get('user')
                cursor = mydb.cursor(buffered=True)
                if query_type == 'sentiment':
                    cursor.execute('SELECT * FROM sentiment_analysis WHERE username = %s AND sdate = %s ORDER BY id ASC', [username, date])
                elif query_type == 'chatbot':
                    cursor.execute('SELECT * FROM chatbot WHERE username = %s AND sdate = %s ORDER BY id ASC', [username, date])
                data = cursor.fetchall()
                cursor.close()
                return render_template('history.html', data=data, query_type=query_type)
            else:
                data = []
                return render_template('history.html', data=data, query_type=query_type)
        
        return render_template('history.html')
    else:
        return redirect(url_for('login'))

@app.route('/about', methods=["GET","POST"])
def about():
    if session.get('user'):
        return render_template('about.html')
    else:
        return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(use_reloader = True, debug= True)
