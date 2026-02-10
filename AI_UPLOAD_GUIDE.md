# 📄 AI-Powered Document Upload

The racebot now supports uploading **PDF, Word (DOCX), and text files** to extract motorsport schedule data using AI!

## 🚀 Quick Setup

### 1. Install Dependencies

```bash
pip install pdfplumber python-docx chardet google-generativeai
```

Or install all dependencies:
```bash
pip install -r requirements.txt
```

### 2. Get a Gemini API Key

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy your API key

### 3. Configure Environment

Add your API key to `.env`:
```bash
GEMINI_API_KEY=your_api_key_here
```

## 📤 How to Use

1. **Navigate to Upload Data tab** in the app
2. **Choose a file**:
   - PDF containing a race schedule
   - Word document (.docx) with event information
   - Plain text file with schedule details
   - JSON (previously exported data)

3. **AI Extraction** (for PDF/Word/Text):
   - The app extracts all text from your document
   - Sends it to Gemini AI for intelligent parsing
   - AI identifies: series name, season, events, dates, venues, sessions
   - Shows you a preview of extracted data

4. **Review & Confirm**:
   - Check the extracted events and validation results
   - Click "Confirm & Load Data" to import

## 💡 Tips

- **File size limit**: 5MB maximum
- **Best results**: Clear, well-structured documents work best
- **Session times**: Include specific times for better extraction
- **Venue info**: More location details = better timezone detection

## 🔧 Troubleshooting

**Error: "GEMINI_API_KEY not set"**
- Make sure you added the key to your `.env` file
- Restart the Streamlit app after setting the env variable

**Error: "Missing dependency"**
- Run `pip install -r requirements.txt`

**Poor extraction results**
- Try a document with clearer formatting (tables work well)
- Check that dates are in recognizable formats
- Ensure series/championship name is mentioned

## 💰 Costs

Gemini 1.5 Flash (used for extraction):
- **Free tier**: 15 requests per minute, 1 million tokens per day
- Typical document uses ~1,000-10,000 tokens
- **Cost**: Effectively free for personal use!

## 🎯 What Gets Extracted

The AI looks for:
- ✅ Championship/Series name
- ✅ Season year
- ✅ Event names and dates
- ✅ Venue information (circuit, city, country)
- ✅ Session details (practice, qualifying, race times)
- ✅ Timezone information

All data is validated using the same validators as other connectors.
