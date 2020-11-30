from flask import Flask,render_template, request, redirect
import requests
import consts
from random import randrange
from apscheduler.schedulers.background import BackgroundScheduler
import json
import time
import random

from hashlib import sha256

app = Flask(__name__)
sched = BackgroundScheduler(daemon=True)    
peers = []
chain = []

def update_peers(peers_list):
    selected_peer = random.choice(peers_list)
    response = requests.get(f"{selected_peer}peers")
    if response.status_code == 200:
        if selected_peer not in peers:
            peers.append(selected_peer)
        for p in response.json()['peers']:
            if p not in peers:
                peers.append(selected_peer)

def chain_messages():
    messages = []
    for tx in chain:
        for m in tx['transactions']:
            add = m
            add['time'] = time.ctime(add['time'])
            messages.append(m)
    return messages

@app.route('/')
def home():
    update_peers([consts.first_peer_contact])
    synchronize_chain()
    return render_template('home.html', msgs = chain_messages())

@app.route('/submit_transaction', methods=['POST'])
def submit_transaction():
    data = { 
            "author": request.form['author'],
            "content": request.form['content'],
            "time": time.time()
            }
    data['hash'] = sha256(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()

    peer = peers[randrange(0,len(peers))]
    print(peers)
    print(f"Chosen peer: {peer}")
    requests.post(peer + "new_transaction", data=json.dumps(data), headers=consts.json_headers)
    return redirect('/')

def synchronize_chain():
    global chain
    peer = peers[randrange(0,len(peers))]
    response = requests.get(peer + 'chain')
    if response.status_code == 200:
        chain = response.json()['chain']


sched.add_job(update_peers, 'interval', args = (peers,), seconds=consts.update_peers_timeout)
sched.start()
if __name__ == '__main__':
    app.run(debug=True)