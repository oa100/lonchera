# 🥡 Lonchera

Lonchera is a Telegram bot that seamlessly integrates with the [Lunch Money](https://lunchmoney.app/) personal finance application, empowering users to effortlessly manage their financial transactions right from Telegram.

# 🔍 Transaction Monitoring
- Periodically checks for new transactions and sends notifications to the user
- Allows users to manually request a list of recent transactions

![img1](media/main.png)

# 🏷️ Transaction Management
For each transaction, users can:
- Change the category
- Add tags
- Add notes
- View Plaid details (if available)
- Mark the transaction as reviewed (or unreviewed)
- Change the payee's name

![video1](media/1.gif)

# 💸 Manual Transactions

- Enables users to manually add transactions for accounts not managed by Plaid

This is very useful when tracking cash or other kinds of accounts.

![video2](media/2.gif)

# 📊 Budget Tracking
- Displays the current state of the user's budget for the current month

![video3](media/3.gif)

# ⚙️ Customizable Settings
- Change the polling interval for new transactions
- Toggle auto-marking of transactions as reviewed
- Manage the Lunch Money API token

![video4](media/4.gif)

# 🚀 Getting Started
1. Clone the repository
2. Set up your Telegram bot token and Lunch Money API token
3. Build and run the Docker container using the provided scripts

Note:

There is an instance of the bot, which is what I am currently using myself, that works:

https://t.me/LunchMoneyAppBot

That said: **DO NOT** plug your personal account to it. I am an honest guy, but this thing is
literally running on a Raspberry Pi in a closet. I can't guarantee that your data is safe,
and I would never use this if I had not built it myself.

Do plug test accounts if you want to. The bot is designed to support multiple users (e.g.
same bot can track transactions for my accounts and for my wife's in her own Telegram account).

Feel free to ask me questions about how to run it yourself. That's why the source code is provided.

# 📄 License
This project is licensed under the [MIT License](LICENSE.md).

---

🍱 Happy expense tracking! 🎉