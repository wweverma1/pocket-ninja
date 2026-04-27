# PocketNinja Backend

PocketNinja is a bilingual, crowdsourced grocery price tracker. This backend service utilizes Vision Large Language Models (VLMs) and OCR to parse crowdsourced receipts, standardizing product data and tracking price histories across various stores to help users find the best local deals. 

## 🚀 Key Features

* **AI-Powered Receipt Analysis:** Extracts products, prices, store names, branch identifiers, and purchase dates from receipt images using Google's Gemini 2.5 Flash model.
* **Intelligent Product Standardization:** Translates, categorizes, and standardizes crowdsourced product names (Japanese/English) while deduplicating catalog entries.
* **Social Authentication:** Seamless and secure user login via Google and LINE OAuth, managed via JWT tokens.
* **Gamification & Leaderboards:** Tracks user contributions, monthly expenditures, and estimated savings, rewarding top contributors with ranks and milestones.
* **Automated Cloud Storage:** Asynchronously optimizes and uploads processed receipt images to Google Drive.
* **Background Processing:** Dedicated background workers handle heavy AI product-matching and database synchronization without blocking user requests.

## 🛠️ Tech Stack

* **Framework:** Python 3 with Flask
* **Database:** MongoDB (via `pymongo`)
* **AI & Computer Vision:** Google GenAI SDK (Gemini)
* **Image Optimization:** Pillow (PIL)
* **Authentication:** PyJWT, Requests-OAuthlib
* **Deployment & Server:** Gunicorn

## 📂 Project Structure

```text
├── app/
│   ├── auth/          # Google & LINE OAuth login flows
│   ├── feedback/      # User rating and feedback submission
│   ├── home/          # Health check endpoints
│   ├── leaderboard/   # User ranking and gamification logic
│   ├── models/        # MongoDB collection wrappers (User, Product, Receipt, etc.)
│   ├── product/       # Receipt upload, validation, and product queries
│   ├── user/          # Profile management, avatars, and receipt history
│   └── utils/         # Core helpers (Gemini AI prompts, Image optimization, Auth, Workers)
├── .env.example       # Example configuration variables
├── requirements.txt   # Python dependencies
├── app.py             # Main Flask application entry point
├── run_worker.py      # Entry point for async product syncing worker
└── generate_token.py  # Utility script for Google Drive OAuth token generation
```

## ⚙️ Prerequisites & Setup

### 1. Environment Variables

Create a `.env` file in the root directory using `.env.example` as a template. You will need the following configurations:

- **App Config:** TARGET_CITY (e.g., Sapporo)  
- **Database:** MONGO_DB_URI, DB_NAME  
- **Security:** JWT_SECRET_KEY  
- **OAuth Credentials:** Google (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) and LINE (LINE_CHANNEL_ID, LINE_CHANNEL_SECRET)  
- **AI Services:** GEMINI_RECEIPT_ANALYSIS_API_KEY, GEMINI_PRODUCT_MATCHING_API_KEY  
- **Cloud Storage:** Google Drive API credentials (GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_REFRESH_TOKEN, etc.)  

### 2. Installation

Install the required Python packages using pip:

```bash
pip install -r requirements.txt
```

### 3. Running the Application

Start the main API server:

```bash
python app.py
```

The server will start on [http://0.0.0.0:5000](http://0.0.0.0:5000).

Start the background worker:

In a separate terminal, run the product synchronization worker to process incoming receipts:

```bash
python run_worker.py
```

## 📡 Core API Endpoints

- **GET /auth/redirect/<provider>:** Initiates Google or LINE login flow.  
- **PUT /product/:** Upload a receipt image (`receiptImage`) for VLM parsing and price extraction.  
- **POST /product/:** Fetch comparative pricing details across different stores for specific `productIds`.  
- **GET /leaderboard/:** Fetch the top 3 contributors and the current user's milestone status.  
- **GET /user/:** Retrieve detailed user profile including ranks, savings, and monthly stats.  
- **PUT /feedback/:** Submit system feedback and app ratings.  

## 🧹 Code Quality

The project utilizes autopep8 for formatting and flake8 for linting. Flake8 is configured to exclude environment folders and enforce a max line length of 120.
