#!/usr/bin/env python3
"""
This will currently only work if you are on the ORNL network and have an ORNL staff account.
"""
import requests
import getpass

USERNAME = input('USERNAME: ')
PASSWORD = getpass.getpass("PASSCODE: ")

response = requests.post(f'https://<your-auth-host>/token', data={
    "username": USERNAME, 'password': PASSWORD,
})
TOKEN = response.json()['access_token']

print("Paste this token into your .env (e.g. as LARGE_MODEL__KEY). Token is valid for 8 hours.")
print(TOKEN)
