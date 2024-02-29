import platform
from flask import Flask, render_template, request, send_file, redirect, url_for, make_response
from fpdf import FPDF
import os
# Conditional import for Gunicorn to ensure compatibility with Windows
if platform.system() != 'Windows':
    from gunicorn.app.base import BaseApplication
from logging_config import configure_logging
import logging

app = Flask(__name__)

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Ticket', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

@app.route("/", methods=["GET", "POST"])
def root_route():
    if request.cookies.get('username'):
        return redirect(url_for('register'))
    if request.method == "POST":
        # Handle POST request if necessary
        pass
    return render_template('login.html')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fname = request.form['fname']
        lname = request.form['lname']
        email = request.form['email']
        ticket_type = request.form['type']
        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"First Name: {fname}", ln=True)
        pdf.cell(200, 10, txt=f"Family Name: {lname}", ln=True)
        pdf.cell(200, 10, txt=f"Email: {email}", ln=True)
        pdf.cell(200, 10, txt=f"Ticket Type: {ticket_type}", ln=True)
        pdf_file_path = f"./tickets/{fname}_{lname}_ticket.pdf"
        os.makedirs(os.path.dirname(pdf_file_path), exist_ok=True)
        try:
            pdf.output(pdf_file_path)
        except Exception as e:
            app.logger.error(f"Failed to save ticket PDF: {e}")
            return "Internal Server Error", 500
        # Save ticket details for purchase history
        ticket_details = {'fname': fname, 'lname': lname, 'email': email, 'type': ticket_type}
        tickets = load_tickets()
        tickets.append(ticket_details)
        try:
            save_tickets(tickets)
        except Exception as e:
            app.logger.error(f"Failed to save ticket details: {e}")
            return "Internal Server Error", 500
        return send_file(pdf_file_path, as_attachment=True)
    else:
        return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        users = load_users()  # Load users from the environment variable
        user = users.get(username)
        if user and user['password'] == password:
            message = "Login successful. Redirecting to ticket page..."
            response = make_response(redirect(url_for('register')))
            response.set_cookie('username', username)
            return response
        else:
            message = "Invalid username or password"
            return render_template('login.html', message=message), 401
    elif request.method == "GET":
        return render_template('login.html')
    else:
        return "Method Not Allowed", 405

@app.route("/logout", methods=["POST"])
def logout():
    response = make_response(redirect(url_for('login')))
    response.set_cookie('username', '', expires=0)
    return response

@app.route("/register_user", methods=["GET", "POST"])
def register_user():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        users = load_users()
        if username in users or email in [user['email'] for user in users.values()]:
            return render_template('register_user.html', message="Username or Email already exists"), 409
        users[username] = {'password': password, 'email': email}
        save_users(users)
        return render_template('register_user.html', message="Registration successful. Redirecting to home page...")
    return render_template('register_user.html')

@app.route("/admin", methods=["GET"])
def admin():
    if not request.cookies.get('username') == 'admin':
        return "Access Denied", 403
    users = load_users()
    return render_template('admin.html', users=users)

@app.route("/admin/edit", methods=["GET", "POST"])
def admin_edit():
    if request.method == "POST":
        username = request.form['username']
        new_name = request.form['new_name']
        new_email = request.form['new_email']
        new_password = request.form['new_password']
        users = load_users()
        if username in users:
            users[username]['name'] = new_name
            users[username]['email'] = new_email
            users[username]['password'] = new_password
            save_users(users)
            return "User details updated successfully", 200
        else:
            return "User not found", 404
    elif request.method == "GET":
        username = request.args.get('username')
        if username:
            return render_template('admin_edit_user.html', username=username)
        else:
            return "User not specified", 400
    else:
        return "Method Not Allowed", 405

@app.route("/admin/delete", methods=["GET"])
def admin_delete():
    if not request.cookies.get('username') == 'admin':
        return "Access Denied", 403
    username = request.args.get('username')
    users = load_users()
    if username in users:
        user_email = users[username]['email']  # Capture user email before deletion
        del users[username]
        save_users(users)
        # Delete user's purchase history
        tickets = load_tickets()
        tickets = [ticket for ticket in tickets if ticket['email'] != user_email]
        save_tickets(tickets)
        return redirect(url_for('admin'))
    else:
        app.logger.error(f"Attempted to delete non-existent user: {username}")
        return "User not found", 404

@app.route("/purchase_history", methods=["GET"])
def purchase_history():
    username = request.cookies.get('username')
    if username != 'admin':
        return "Access Denied", 403
    # Retrieve user's purchase history
    tickets = load_tickets()
    return render_template('purchase_history.html', tickets=tickets)

# StandaloneApplication class definition is now conditional
if platform.system() != 'Windows':
    class StandaloneApplication(BaseApplication):
        def __init__(self, app, options=None):
            self.application = app
            self.options = options or {}
            super().__init__()

        def load_config(self):
            config = {
                key: value
                for key, value in self.options.items()
                if key in self.cfg.settings and value is not None
            }
            for key, value in config.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self.application

import json

def load_users():
    try:
        with open('users_data.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_users(users):
    with open('users_data.json', 'w') as file:
        json.dump(users, file)

def load_tickets():
    try:
        with open('tickets_data.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def save_tickets(tickets):
    with open('tickets_data.json', 'w') as file:
        json.dump(tickets, file)

users = load_users()

if __name__ == "__main__":
    configure_logging()
    app.run(host="0.0.0.0", port=5000)
else:
    options = {"bind": "%s:%s" % ("0.0.0.0", "5000"), "workers": 4, "loglevel": "info"}
    StandaloneApplication(app, options).run()