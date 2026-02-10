"""
Direct test of MotoGP calendar page with better waiting and debugging.
"""
import asyncio
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv

load_dotenv()


async def test_motogp_calendar():
    """Test fetching MotoGP calendar with proper waiting."""
    url = "https://www.motogp.com/en/calendar"
    
    print(f"Testing MotoGP Calendar: {url}\n")
    
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Wait a bit more for JavaScript to render
        print("Waiting for page to fully render...")
        await asyncio.sleep(3)
        
        # Get the page title
        title = await page.title()
        print(f"Page title: {title}\n")
        
        # Check if we have calendar content
        print("Checking for calendar elements...")
        
        # Try to find race cards or event elements
        race_cards = await page.query_selector_all(".race-card, .event-card, .calendar-event")
        print(f"Found {len(race_cards)} race card elements")
        
        # Look for date elements
        dates = await page.query_selector_all("[class*='date'], [class*='Date']")
        print(f"Found {len(dates)} date elements")
        
        # Look for race names
        races = await page.query_selector_all("[class*='race'], [class*='event'], [class*='grand-prix']")
        print(f"Found {len(races)} race/event elements")
        
        # Get some sample text from the page
        print("\nSample content from page:")
        body_text = await page.inner_text("body")
        
        # Check if we have calendar-related keywords
        keywords = ["Grand Prix", "Circuit", "Round", "2025", "2024"]
        for keyword in keywords:
            if keyword in body_text:
                print(f"  ✅ Found '{keyword}' in page content")
            else:
                print(f"  ❌ '{keyword}' not found")
        
        # Save the HTML for inspection
        html = await page.content()
        cache_file = ".cache/motogp_calendar_debug.html"
        os.makedirs(".cache", exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n📄 Saved HTML to: {cache_file}")
        print(f"   Content size: {len(html):,} bytes")
        
        # Take a screenshot
        screenshot_file = ".cache/motogp_calendar_debug.png"
        await page.screenshot(path=screenshot_file)
        print(f"📸 Saved screenshot to: {screenshot_file}")
        
        await browser.close()
        
        print("\n" + "="*60)
        print("Analysis:")
        if "Calendar" in title or "calendar" in body_text.lower()[:1000]:
            print("✅ Looks like we're on the calendar page")
        else:
            print("⚠️ Doesn't look like the calendar page")
            print(f"   Title suggests: {title}")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(test_motogp_calendar())
