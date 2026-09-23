# Google Maps Setup Guide for Q-ROUTE

This guide explains how to configure Google Maps for the Q-ROUTE application. Note that Google Maps is **optional** - the application works perfectly with Leaflet and OpenStreetMap without any API key.

## Why Use Google Maps?

- **Better map quality**: More detailed and up-to-date maps in many regions
- **Places Autocomplete**: Enhanced location search with suggestions
- **Better performance**: Optimized rendering and interaction
- **Additional features**: Street View, satellite imagery, etc.

## Prerequisites

- Google Cloud account (free tier available)
- Valid credit card (required by Google Cloud, but you won't be charged for typical usage)
- Basic understanding of Google Cloud Console

## Step-by-Step Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Click "New Project"
4. Enter a project name (e.g., "Q-ROUTE Navigation")
5. Click "Create"

### 2. Enable Required APIs

1. In the Google Cloud Console, navigate to **APIs & Services > Library**
2. Search for and enable the following APIs:

   **Required:**
   - **Maps JavaScript API** - For displaying maps
   - **Geocoding API** - For converting addresses to coordinates
   - **Places API** - For location search and autocomplete

   **Optional (for advanced features):**
   - **Directions API** - For enhanced routing (note: Q-ROUTE uses its own routing)
   - **Traffic Layer** - For real-time traffic visualization

3. Click on each API and press the "Enable" button

### 3. Create API Key

1. Navigate to **APIs & Services > Credentials**
2. Click "Create Credentials"
3. Select "API Key"
4. Your API key will be generated and displayed

### 4. Restrict API Key (Important for Security)

1. Click on the "Edit" icon (pencil) next to your API key
2. Under "Application restrictions", choose one of the following:

   **Option A: HTTP Referrers (Recommended for web apps)**
   - Select "HTTP referrers"
   - Add your domain(s):
     - For local development: `http://localhost:*`
     - For production: `https://yourdomain.com/*`
     - For multiple domains: Add each one on a new line

   **Option B: IP Addresses (For server-side calls)**
   - Select "IP addresses"
   - Add your server IP addresses

3. Under "API restrictions", select "Restrict key"
4. Select only the APIs you enabled in Step 2:
   - Maps JavaScript API
   - Geocoding API
   - Places API
   - (Optional) Directions API, Traffic Layer

5. Click "Save"

### 5. Configure Q-ROUTE to Use Your API Key

You have several options to configure the API key in Q-ROUTE:

#### Option 1: Meta Tag (Recommended for Development)

Add this meta tag to the `<head>` section of `frontend/index.html`:

```html
<meta name="google-maps-api-key" content="YOUR_API_KEY_HERE">
```

Replace `YOUR_API_KEY_HERE` with your actual API key.

#### Option 2: JavaScript Variable

Add this to `frontend/script.js` before the initialization code:

```javascript
window.GOOGLE_MAPS_API_KEY = 'YOUR_API_KEY_HERE';
```

#### Option 3: Local Storage (For Testing)

Run this in your browser's console:

```javascript
localStorage.setItem('google_maps_api_key', 'YOUR_API_KEY_HERE');
```

#### Option 4: Environment Variable (For Production)

If you're using a build process or server-side rendering, set the environment variable:

```bash
export GOOGLE_MAPS_API_KEY="YOUR_API_KEY_HERE"
```

Then access it in your code:

```javascript
const apiKey = process.env.GOOGLE_MAPS_API_KEY;
```

### 6. Configure Map Provider

In `frontend/script.js`, modify the map initialization to use Google Maps:

```javascript
// Find this line in the init() function
await mapProvider.initialize('map', center, 12, {
  provider: 'leaflet', // Change this to 'google'
});

// Change to:
await mapProvider.initialize('map', center, 12, {
  provider: 'google',
});
```

### 7. Test the Configuration

1. Start your backend server
2. Open the frontend in your browser
3. Check the browser console for any Google Maps errors
4. Verify that the map loads correctly
5. Test location search and route optimization

## Usage Limits and Pricing

### Free Tier (Google Cloud $300 Credit)

New Google Cloud accounts receive $300 in free credits, which is sufficient for development and testing.

### Standard Pricing (After Free Credit)

As of 2024, the pricing for the required APIs is approximately:

- **Maps JavaScript API**: $7 per 1,000 loads (first 28,000/month free)
- **Geocoding API**: $5 per 1,000 requests (first 40,000/day free)
- **Places API**: $32 per 1,000 requests (varies by request type)

### Monthly Free Quotas

- Maps JavaScript API: 28,000 free map loads per month
- Geocoding API: 40,000 free requests per day
- Places API: Varies by request type

For typical Q-ROUTE usage (development and moderate testing), you're unlikely to exceed these free quotas.

## Monitoring Usage

1. Go to **APIs & Services > Dashboard** in Google Cloud Console
2. Select your API key
3. View usage metrics for each API
4. Set up budget alerts if needed

## Troubleshooting

### "RefererNotAllowedMapError"

This error means your API key's HTTP referrer restrictions don't match your current domain.

**Solution:**
- Update the HTTP referrer restrictions in Google Cloud Console
- Include your current domain (e.g., `http://localhost:*` for local development)

### "ApiNotActivatedMapError"

This error means the required API is not enabled.

**Solution:**
- Go to APIs & Services > Library
- Enable the Maps JavaScript API

### "MissingKeyMapError"

This error means no API key is configured or detected.

**Solution:**
- Verify your API key is configured using one of the methods in Step 5
- Check the browser console for configuration errors

### Map Loads But No Tiles

This could be a billing issue or API restriction problem.

**Solution:**
- Verify billing is enabled in Google Cloud Console
- Check that all required APIs are enabled
- Verify API key restrictions

## Switching Back to Leaflet

If you want to switch back to Leaflet (OpenStreetMap):

1. Remove or comment out the Google Maps API key configuration
2. In `script.js`, change the provider back to 'leaflet':
   ```javascript
   await mapProvider.initialize('map', center, 12, {
     provider: 'leaflet',
   });
   ```
3. The application will automatically use OpenStreetMap tiles

## Best Practices

1. **Security**: Always restrict your API key to specific domains
2. **Monitoring**: Regularly check your usage in Google Cloud Console
3. **Billing**: Set up budget alerts to avoid unexpected charges
4. **Development**: Use separate API keys for development and production
5. **Rate Limiting**: Implement client-side rate limiting to avoid quota exhaustion
6. **Fallback**: Keep Leaflet as a fallback in case of Google Maps issues

## Additional Resources

- [Google Maps Platform Documentation](https://developers.google.com/maps/documentation)
- [Google Cloud Console](https://console.cloud.google.com/)
- [Google Maps Pricing](https://cloud.google.com/maps-platform/pricing)
- [API Key Best Practices](https://support.google.com/googleapi/answer/6310037)

## Support

If you encounter issues specific to Q-ROUTE integration:

1. Check the main Q-ROUTE documentation
2. Verify your backend is running correctly
3. Check browser console for error messages
4. Ensure all required APIs are enabled
5. Verify API key restrictions match your domain

## Conclusion

Google Maps integration provides enhanced map quality and features for Q-ROUTE, but it's entirely optional. The application works perfectly with Leaflet and OpenStreetMap, which are free and don't require API keys. Choose the option that best fits your needs and budget.
