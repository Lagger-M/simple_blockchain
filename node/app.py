import json
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.hazmat.primitives import serialization
from flask import Flask, request
from copy import deepcopy

import consts
from block import Block
from blockchain import BlockChain
from node import Node

app = Flask(__name__)
node = Node()
# Contains the host addresses of other participating members of the network
sched = BackgroundScheduler(daemon=True)


def send_keep_alive():
    node.peer_timeout_update()
    data = {"node_address": node.host,
            "time": time.time()}
    msg = node.create_message(data)

    for peer in node.peers:
        try:
            requests.post(peer + "/keep_alive", data=json.dumps(msg), headers=consts.json_headers)
        except requests.exceptions.ConnectionError:
            pass


@app.route('/keep_alive', methods=['POST'])
def receive_keep_alive():
    msg = request.get_json()["msg"]
    if node.verify_message(request.get_json()):
        node.peer_keep_alive_update(msg)
        return "Keep alive received", 200
    return "Signature verification failed",400


@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]

    for field in required_fields:
        if not tx_data.get(field):
            return "Invalid transaction data", 404

    node.blockchain.add_new_transaction(tx_data)

    # announce transaction to other nodes
    for peer in node.peers:
        print(f"announcing transaction to node: {peer}")
        requests.post(peer + "/announce_transaction", data=json.dumps(tx_data), headers=consts.json_headers)
    return "Success", 201


@app.route('/announce_transaction', methods=['POST'])
def announce_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]

    for field in required_fields:
        if not tx_data.get(field):
            return "Invalid transaction data", 404

    node.blockchain.add_new_transaction(tx_data)
    return "Success", 201


@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    for block in node.blockchain.chain:
        chain_data.append(block.__dict__)
    return {"length": len(chain_data), "chain": chain_data}


@app.route('/pending_transactions', methods=['GET'])
def get_pending_transactions():
    return json.dumps({"unconfirmed_transactions": node.blockchain.unconfirmed_transactions})


@app.route('/peers', methods=['GET'])
def return_peers():
    return json.dumps({"peers": node.peers})


@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    if len(node.blockchain.unconfirmed_transactions) != 0:
        result = node.blockchain.mine()

        # Making sure we have the longest chain before announcing to the network
        chain_length = len(node.blockchain.chain) - 1
        consensus()
        if chain_length == len(node.blockchain.chain):
            # announce the recently mined block to the network
            announce_new_block(node.blockchain.last_block())
            return "Block #{} is mined.".format(result)


@app.route('/update_peers', methods=['POST'])
def update_peers():
    print(f"received update peers {request.get_json()}")
    msg = request.get_json()["msg"]
    if node.verify_message(request.get_json()):
        if "peers" not in msg:
            return "Invalid data", 400
        for p in [p for p in msg["peers"] if p["node_address"] != request.host_url]:
            node.peer_management([p])
        return "Peers updated"


# Endpoint to add new peers to the network
@app.route('/register_node', methods=['POST'])
def register_new_peers():
    node.host = request.host_url

    data = request.get_json()["msg"]
    if list(data.keys()).sort() != consts.register_node_fields.sort():
        return "Invalid data", 400

    # Add the node to the peer list
    node.peer_management([data])

    peers_to_announce = []
    for p in node.peers:
        peer_dict = {}
        peer_dict["node_address"] = p
        peer_dict["public_key"] = node.peers[p]["public_key"]
        peers_to_announce.append(peer_dict)

    print(f"peers to announce: {peers_to_announce}")
    # Announce node to peers
    data_to_send = {"node_address": node.host,
                    "peers": peers_to_announce}


    msg = node.create_message(data_to_send)
    for peer in [p for p in node.peers if p != data["node_address"]]:
        requests.post(peer + "/update_peers", data=json.dumps(msg), headers=consts.json_headers)

    # Return the blockchain to the newly registered node so that it can sync
    data_to_send = {"node_address": node.host,
                    "public_key": node.public_key,
                    "blockchain": get_chain(),
                    "peers": peers_to_announce}
    msg = node.create_message(data_to_send)
    return json.dumps(msg)


@app.route('/register_with', methods=['POST'])
def register_with_existing_node():
    """
    Internally calls the `register_node` endpoint to
    register current node with the remote node specified in the
    request, and sync the blockchain as well with the remote node.
    """
    node.host = request.host_url
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    data = {"node_address": request.host_url,
            "public_key": node.public_key}
    msg = node.create_message(data)

    # Make a request to register with remote node and obtain information
    response = requests.post(node_address + "/register_node", data=json.dumps(msg), headers=consts.json_headers)

    if response.status_code == 200:
        data = response.json()["msg"]
        chain_dump = data.pop("blockchain")['chain']
        # update chain and the peers
        node.peer_management([data])
        for p in [p for p in data["peers"] if p["node_address"] != request.host_url]:
            node.peer_management([p])

        # Sync blockchain
        node.blockchain = node.create_chain_from_dump(chain_dump)
        return "Registration successful", 200
    else:
        # if something goes wrong, pass it on to the API response
        return response.content, response.status_code


@app.route('/add_block', methods=['POST'])
def verify_and_add_block():
    block_data = request.get_json()
    block = Block(block_data["id"],
                  block_data["transactions"],
                  block_data["timestamp"],
                  block_data["previous_hash"],
                  block_data["nonce"])
    block.hash = block_data['hash']
    added = node.blockchain.add_block(block)

    if not added:
        return "The block was discarded by the node", 400
    return "Block added to the chain", 201


def announce_new_block(block):
    """
    A function to announce to the network once a block has been mined.
    Other blocks can simply verify the proof of work and add it to their
    respective chains.
    """
    for peer in node.peers:
        url = f"{peer}add_block"
        requests.post(url, data=json.dumps(block.__dict__, sort_keys=True), headers=consts.json_headers)

def consensus():
    """
    If a longer valid chain is found, chain is replaced with it.
    """

    longest_chain = node.blockchain.chain
    current_len = len(longest_chain)

    for peer in node.peers:
        response = requests.get(f'{peer}/chain')
        length = response.json()['length']
        chain = response.json()['chain']
        peer_blockchain = node.create_chain_from_dump(chain)
        if length >= current_len and node.blockchain.check_chain_validity(peer_blockchain.chain):
            current_len = length
            longest_chain = chain

    node.blockchain.chain = longest_chain


sched.add_job(send_keep_alive, 'interval', seconds=consts.keep_alive_timeout)
sched.add_job(mine_unconfirmed_transactions, 'interval', seconds=consts.block_timeout)
sched.start()

if __name__ == '__main__':
    app.run(debug=True)
