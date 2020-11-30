import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa

import consts
from blockchain import BlockChain
from block import Block


class Node:
    def __init__(self):
        self.blockchain = BlockChain(consts.difficulty)
        self.blockchain.create_genesis_block()

        self.private_key = rsa.generate_private_key(public_exponent=consts.rsa_public_exponent,
                                                    key_size=consts.rsa_key_size, backend=default_backend())
        # Storing public key as serialized string
        self.public_key = self.private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM,
                                                                     format=serialization.PublicFormat.SubjectPublicKeyInfo).decode(
            'ascii')
        self._peers = {}
        self.host = ''

    @property
    def peers(self):
        encoded_peers = {}
        for p in self._peers:
            encoded_peers[p] = {}
            for key in self._peers[p]:
                if key == "public_key":
                    pk = self._peers[p]["public_key"]
                    pk_serialized = pk.public_bytes(encoding=serialization.Encoding.PEM,
                                                    format=serialization.PublicFormat.SubjectPublicKeyInfo)
                    ascii_pk = pk_serialized.decode('ascii')
                    encoded_peers[p]["public_key"] = ascii_pk
                else:
                    encoded_peers[p][key] = self._peers[p][key]
        return encoded_peers

    def sign(self, message: str):
        return base64.b64encode(self.private_key.sign(message.encode(),
                                     padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                 salt_length=padding.PSS.MAX_LENGTH),
                                     hashes.SHA256())).decode('ascii')

    def verify(self, message: bytes, signature: bytes, key: rsa.RSAPublicKey):
        try:
            key.verify(signature, message,
                       padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                       hashes.SHA256())
            return True
        except InvalidSignature:
            return False

    def peer_timeout_update(self):
        to_del = []
        for peer in self._peers:
            self._peers[peer]["timeout"] -= 1
            if self._peers[peer]["timeout"] == 0:
                to_del.append(peer)

        for peer in to_del:
            self._peers.pop(peer, None)

    def peer_keep_alive_update(self, msg):
        if "node_address" in msg and msg["node_address"] in self._peers:
            peer_addr = msg["node_address"]
            self._peers[peer_addr]["timeout"] = consts.peer_timeout
            print(f"received keep alive from: {peer_addr}")

    def peer_management(self, peer_list):
        for p in peer_list:
            if p["node_address"] not in self._peers:
                self._peers[p["node_address"]] = {}
                self._peers[p["node_address"]]["timeout"] = consts.peer_timeout

                pk_bytes = p["public_key"].encode()
                pk = serialization.load_pem_public_key(pk_bytes, backend=default_backend())
                self._peers[p["node_address"]]["public_key"] = pk
            else:
                self._peers[p["node_address"]]["timeout"] = consts.peer_timeout

    def create_message(self, data: dict):
        msg = {"msg": data, "signature": self.sign(json.dumps(data, sort_keys=True))}
        return msg

    def verify_message(self, msg):
        signature = base64.b64decode(msg.pop("signature").encode())
        peer = msg["msg"]["node_address"]
        dump = json.dumps(msg["msg"], sort_keys=True)
        if self.verify(dump.encode(), signature, self._peers[peer]["public_key"]):
            return True
        return False

    def create_chain_from_dump(self,chain_dump):
        new_blockchain = BlockChain(consts.difficulty)
        for idx, block_data in enumerate(chain_dump):
            block = Block(block_data["id"],
                        block_data["transactions"],
                        block_data["timestamp"],
                        block_data["previous_hash"],
                        block_data["nonce"])
            block.hash = block_data['hash']

            if idx > 0:
                added = new_blockchain.add_block(block)
                if not added:
                    raise Exception("The chain dump is tampered!!")
            else:  # the block is a genesis block, no verification needed
                new_blockchain.chain.append(block)

        return new_blockchain
