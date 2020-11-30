import json

from hashlib import sha256


class Block:
    def __init__(self, id: int, transactions: list, timestamp: float, previous_hash: str, nonce: int = 0):
        """
        Constructor for Block class
        :param previous_hash: Hash of the previous block
        :param id: Unique ID of block
        :param transactions: List of transactions
        :param timestamp: Time of block generation
        """
        self.id = id
        self.transactions = transactions
        self.nonce = nonce
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """
        Return hash of whole block instance after converting to JSON
        :return: sha256 hash
        """
        #block_dict = self.__dict__.pop('hash', None)  # Remove hash field value before calculating hash
        block_dict = self.__dict__.copy()
        block_dict.pop('hash', None) # Remove hash field value before calculating hash
        block_string = json.dumps(block_dict, sort_keys=True).encode('utf-8')
        return sha256(block_string).hexdigest()
