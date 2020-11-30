from time import time

from block import Block


class BlockChain:
    """Blockchain Class"""
    genesis_block_previous_hash = '0'  # previous hash of genesis block

    def __init__(self, difficulty: int) -> None:
        """
        Class initialization
        :param difficulty: Specifies difficulty of PoW algorithm, defines number zeroes at the start
        """
        self.unconfirmed_transactions = []  # transactions waiting for adding to the chain
        self.chain = []
        self.difficulty = difficulty

    def create_genesis_block(self) -> None:
        """
        Creates first block in blockchain
        """
        genesis_block = Block(0, [], time(), BlockChain.genesis_block_previous_hash)
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    def last_block(self) -> Block:
        """
        Return last block in the chain
        :return: Block object
        """
        return self.chain[-1]

    def proof_of_work(self, block: Block) -> str:
        """
        Finds nonce to fulfill difficulty requirements
        :param block: Block object
        :return: hash
        """
        block.nonce = 0
        hash = block.compute_hash()
        while not hash.startswith('0' * self.difficulty):
            block.nonce += 1
            hash = block.compute_hash()
        return hash

    def add_block(self, block: Block):
        """
        Add block to blockchain if following requirements are fulfilled:
            - proof hash has required number of starting zeros
            - proof hash equals hash of block
            - block previous_hash equals hash of previous block
        Delete transactions in unconfirmed transaction list which have been mined in this block
        :param block: Block object
        :return:
        """
        if self.last_block().hash == block.previous_hash and self.hash_valid_proof(block):
            self.chain.append(block)

            tx_to_del = []
            for tx in block.transactions:
                if tx in self.unconfirmed_transactions:
                    tx_to_del.append(tx)
            self.unconfirmed_transactions = [tx for tx in self.unconfirmed_transactions if tx not in tx_to_del]
            return True
        return False

    def hash_valid_proof(self, block: Block):
        return block.hash.startswith('0' * self.difficulty) and block.hash == block.compute_hash()

    def add_new_transaction(self, transaction):
        self.unconfirmed_transactions.append(transaction)

    def mine(self):
        if not self.unconfirmed_transactions:
            return False
        block = Block(self.last_block().id + 1, self.unconfirmed_transactions, time(), self.last_block().hash)
        block.hash = self.proof_of_work(block)
        self.add_block(block)
        self.unconfirmed_transactions = []
        return block.id

    def check_chain_validity(self, chain):
        """
        Checks if entire chain is valid
        :param chain: chain to check
        :return: True if correct, False if incorrect
        """
        previous_hash = BlockChain.genesis_block_previous_hash

        for block in chain:
            if block.previous_hash != previous_hash or block.hash != block.compute_hash():
                return False
            previous_hash = block.previous_hash
        return True
