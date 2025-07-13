from binance.client import Client

api_key = 'klyrsaNkaedXJf1lxJk20KXn2pLi8BhaZwTzQ2TKeepbw6cCqlraB7urCXPwTTj8'
api_secret = 'xjsgvuX2QORjF6vAVpGHFmjNecDuyIhz3n2GAT3yCmnzwBXG1XCc7hGT0YJCHsue'

client = Client(api_key, api_secret)
account = client.a
print(account)