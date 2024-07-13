# 🥡 Lonchera

Lonchera is a Telegram bot that seamlessly integrates with the Lunch Money personal finance application, empowering users to effortlessly manage their financial transactions right from their Telegram chat.

## 🌟 Key Features

### 🔍 Transaction Monitoring
- Periodically checks for new transactions and sends notifications to the user
- Allows users to manually request a list of recent transactions
- Provides a list of pending transactions

### 🏷️ Transaction Management
For each transaction, users can:
- Change the category
- Add tags
- Add notes
- View Plaid details (if available)
- Mark the transaction as reviewed

### 💸 Manual Transactions
- Enables users to manually add transactions for accounts not managed by Plaid

### 🔄 Plaid Integration
- Triggers a refresh of transactions from Plaid, ensuring data is always up to date

### 📊 Budget Tracking
- Displays the current state of the user's budget for the current month

### ⚙️ Customizable Settings
- Change the polling interval for new transactions
- Toggle auto-marking of transactions as reviewed
- Manage the Lunch Money API token
- Log out of the bot

## 🛠️ Technologies Used
- Python
- python-telegram-bot: Telegram Bot API integration
- SQLAlchemy: Database management
- Lunchable: Lunch Money API client
- Docker: Containerization for easy deployment

## 🚀 Getting Started
1. Clone the repository
2. Set up your Telegram bot token and Lunch Money API token
3. Build and run the Docker container using the provided scripts

## 🤝 Contributing
We welcome contributions from the community! Please refer to our [contribution guidelines](CONTRIBUTING.md) for more information.

## 📄 License
This project is licensed under the [MIT License](LICENSE.md).

---

🍱 Happy expense tracking with Lonchera! 🎉