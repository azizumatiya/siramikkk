from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
import bcrypt
from functools import wraps
from dotenv import load_dotenv
import os

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key')

# Load environment variables
load_dotenv()

# MongoDB connection
client = MongoClient('mongodb+srv://umatiyaaziz2004_db_user:lkCvLsRTypDho7Wx@siramik.k3vxnao.mongodb.net/')
db = client['siramik_welding']
users_collection = db['users']
invoices_collection = db['invoices']
invoice_counter_collection = db['invoice_counter']

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Initialize invoice counter
def init_invoice_counter():
    if invoice_counter_collection.count_documents({}) == 0:
        invoice_counter_collection.insert_one({'_id': 'invoice_number', 'seq': 1})

# Get next invoice number
def get_next_invoice_number():
    counter = invoice_counter_collection.find_one_and_update(
        {'_id': 'invoice_number'},
        {'$inc': {'seq': 1}},
        return_document=True
    )
    return f"G2FEE{counter['seq']:03d}"

# Routes

@app.route('/')
@login_required
def index():
    return redirect(url_for('billing'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        user = users_collection.find_one({'mobile': mobile})
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            flash('Login successful!', 'success')
            return redirect(url_for('billing'))
        else:
            flash('Invalid mobile number or password.', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        if users_collection.find_one({'mobile': mobile}):
            flash('Mobile number already registered.', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        users_collection.insert_one({
            'mobile': mobile,
            'password': hashed_password
        })
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/billing')
@login_required
def billing():
    stats = get_stats()
    return render_template('billing.html', stats=stats)

@app.route('/saved_invoices')
@login_required
def saved_invoices():
    stats = get_stats()
    return render_template('saved_invoices.html', stats=stats)

@app.route('/monthly_report')
@login_required
def monthly_report():
    stats = get_stats()
    return render_template('monthly_report.html', stats=stats)

@app.route('/api/invoice-number')
@login_required
def get_invoice_number():
    return jsonify({'number': get_next_invoice_number()})

@app.route('/api/invoices', methods=['GET', 'POST'])
@login_required
def invoices():
    if request.method == 'POST':
        data = request.get_json()
        data['created_at'] = datetime.utcnow()
        result = invoices_collection.insert_one(data)
        return jsonify({'success': True, 'id': str(result.inserted_id)})
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = {}
    if start_date and end_date:
        query['created_at'] = {
            '$gte': datetime.fromisoformat(start_date.replace('Z', '+00:00')),
            '$lte': datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        }
    
    invoices = list(invoices_collection.find(query))
    for invoice in invoices:
        invoice['_id'] = str(invoice['_id'])
    return jsonify(invoices)

@app.route('/api/invoices/search')
@login_required
def search_invoices():
    name = request.args.get('name')
    address = request.args.get('address')
    
    query = {}
    if name:
        query['name'] = {'$regex': name, '$options': 'i'}
    if address:
        query['address'] = {'$regex': address, '$options': 'i'}
    
    invoices = list(invoices_collection.find(query))
    for invoice in invoices:
        invoice['_id'] = str(invoice['_id'])
    return jsonify(invoices)

@app.route('/api/invoices/<id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def invoice(id):
    try:
        invoice_id = ObjectId(id)
    except:
        return jsonify({'error': 'Invalid invoice ID'}), 400
    
    if request.method == 'GET':
        invoice = invoices_collection.find_one({'_id': invoice_id})
        if not invoice:
            return jsonify({'error': 'Invoice not found'}), 404
        invoice['_id'] = str(invoice['_id'])
        return jsonify(invoice)
    
    if request.method == 'PUT':
        data = request.get_json()
        data['updated_at'] = datetime.utcnow()
        result = invoices_collection.update_one(
            {'_id': invoice_id},
            {'$set': data}
        )
        if result.modified_count:
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found'}), 404
    
    if request.method == 'DELETE':
        result = invoices_collection.delete_one({'_id': invoice_id})
        if result.deleted_count:
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found'}), 404

def get_stats():
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    end_of_month = datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1)
    
    invoices = invoices_collection.find({
        'created_at': {'$gte': start_of_month, '$lt': end_of_month}
    })
    
    monthly_count = 0
    total_paid = 0
    total_balance = 0
    
    for invoice in invoices:
        monthly_count += 1
        total_paid += invoice.get('amountPaid', 0)
        total_balance += invoice.get('total', 0) - invoice.get('amountPaid', 0)
    
    return {
        'monthly_count': monthly_count,
        'total_paid': total_paid,
        'total_balance': total_balance
    }

if __name__ == '__main__':
    init_invoice_counter()
    app.run(debug=True)