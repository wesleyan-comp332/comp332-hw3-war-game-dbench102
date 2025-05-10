"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = []


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    data = bytearray()
    remainder = numbytes #sock.recv might return less data than needed
    
    while remainder > 0:
        chunk = sock.recv(remainder)
        if not chunk: #End of the File
            break
        #make necessary adjustments
        data.extend(chunk)
        remainder -= len(chunk)
    
    return bytes(data)

def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    try:
        if game.p1:
            game.p1.close()
    except:
        pass
    
    try:
        if game.p2:
            game.p2.close()
    except:
        pass


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    # % 13 allows for cards to be compared as the 52 card deck increases by suit
    if (card1 % 13) < (card2 % 13): 
        return -1
    elif (card1 % 13) == (card2 % 13):
        return 0
    elif (card1 % 13) > (card2 % 13):
        return 1
    
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    deck = list(range(52))
    random.shuffle(deck)
    #divide deck in half per player
    player1 = deck[:26]
    player2 = deck[26:]
    
    return player1, player2
    
    

def serve_game(host, port):
    """
    Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    #create socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #bind to host and port
    server_socket.bind((host, port))
    #listen for the 2 connections
    server_socket.listen(2) 
    
    print(f"Server started on {host}:{port}")
    
    #run forever
    while True:
        # wait for two clients
        if len(waiting_clients) < 2:
            try:
                #new client connection
                client_sock, client_addr = server_socket.accept()
                print(f"New connection from {client_addr}")
                #queue
                waiting_clients.append(client_sock)
                #continue waiting for 2 clients
                if len(waiting_clients) < 2:
                    continue
            except Exception as e:
                print(f"Error accepting connection: {e}")
                continue
        
        #starting the game
        if len(waiting_clients) >= 2:
            p1_sock = waiting_clients.pop(0)
            p2_sock = waiting_clients.pop(0)
            #game object
            game = Game(p1=p1_sock, p2=p2_sock)
            #new thread
            war_thread = threading.Thread(target=play_war, args=(game,))
            war_thread.daemon = True
            war_thread.start()

def play_war(game):
    """
    Succesfully play a game of war
    """
    try:
        #wait for command
        p1_command = readexactly(game.p1, 2)
        p2_command = readexactly(game.p2, 2)
        #verify command
        if (p1_command[0] != Command.WANTGAME.value or p1_command[1] != 0 or p2_command[0] != Command.WANTGAME.value or p2_command[1] != 0):
            print("invalid game request")
            kill_game(game)
            return
        #deal cards
        p1_hand, p2_hand = deal_cards()
        #send game start msg
        p1_msg = bytes([Command.GAMESTART.value]) + bytes(p1_hand)
        p2_msg = bytes([Command.GAMESTART.value]) + bytes(p2_hand)
        game.p1.sendall(p1_msg)
        game.p2.sendall(p2_msg)
        
        #26 rounds bc 52 cards in deck
        for i in range(26):
            #get cards 
            p1_play = readexactly(game.p1, 2)
            p2_play = readexactly(game.p2, 2)
            #verify command
            if (p1_play[0] != Command.PLAYCARD.value or p2_play[0] != Command.PLAYCARD.value):
                print("invalid play card request")
                kill_game(game)
                return
            # get card vals
            p1_card = p1_play[1]
            p2_card = p2_play[1]
            # compare cards
            result = compare_cards(p1_card, p2_card)
            #determine the results
            if result > 0: #p1 win
                p1_result = Result.WIN.value
                p2_result = Result.LOSE.value
            elif result < 0: #p2 win
                p1_result = Result.LOSE.value
                p2_result = Result.WIN.value
            else: #tie
                p1_result = Result.DRAW.value
                p2_result = Result.DRAW.value
            
            #send results
            game.p1.sendall(bytes([Command.PLAYRESULT.value, p1_result]))
            game.p2.sendall(bytes([Command.PLAYRESULT.value, p2_result]))
        
        # close connection
        kill_game(game)
    except Exception as e:
        print(f"error during game: {e}")
        kill_game(game)

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
