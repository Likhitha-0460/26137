# Q-ROUTE Frontend

Quantum-Inspired Traffic Intelligence - Google Maps-inspired navigation interface

## Features

- **Google Maps-Inspired UI**: Clean, modern navigation interface similar to Google Maps
- **Map Provider Abstraction**: Supports both Google Maps and Leaflet with automatic fallback
- **Real-time Route Optimization**: Compares Dijkstra, A*, and Quantum-Inspired Genetic Algorithm (QIGA)
- **Traffic-Aware Routing**: Uses real Bengaluru traffic data for congestion-aware routing
- **Interactive Map**: Full-screen map with floating panels and intuitive controls
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices
- **Location Search**: Autocomplete-powered location search with geocoding
- **Performance Analytics**: Charts and metrics comparing algorithm performance
- **QIGA Insights**: Technical explanation of the quantum-inspired optimization process

## File Structure

```
frontend/
├── index.html          # Main HTML structure
├── style.css           # Google Maps-inspired styling
├── script.js           # Main application logic
├── map.js              # Map provider abstraction layer
├── api.js              # API service layer
└── README.md           # This file
```

## Setup Instructions

### Prerequisites

- Node.js (optional, for development)
- Backend server running on port 5000 (or configured port)
- Internet connection for map tiles and geocoding

### Quick Start

1. **Ensure Backend is Running**
   ```bash
   cd backend
   python app.py
   ```

2. **Open Frontend**
   - Simply open `index.html` in a web browser, or
   - Use a local server (recommended):
     ```bash
     # Using Python
     cd frontend
     python -m http.server 8000
     
     # Using Node.js (if you have http-server installed)
     npx http-server -p 8000
     ```

3. **Access the Application**
   - Open `http://localhost:8000` in your browser

### Google Maps Integration (Optional)

The application works out of the box with Leaflet and OpenStreetMap. To use Google Maps instead:

1. **Get a Google Maps API Key**
   - Follow the instructions in `GOOGLE_MAPS_SETUP.md`
   - Create a Google Cloud project
   - Enable the required APIs
   - Create and restrict your API key

2. **Configure the API Key**
   
   You can set the Google Maps API key in one of these ways:
   
   **Option 1: Meta Tag (Recommended for development)**
   ```html
   <!-- In index.html, add this meta tag in the <head> section -->
   <meta name="google-maps-api-key" content="YOUR_API_KEY_HERE">
   ```
   
   **Option 2: JavaScript Variable**
   ```javascript
   // In script.js, before initialization
   window.GOOGLE_MAPS_API_KEY = 'YOUR_API_KEY_HERE';
   ```
   
   **Option 3: Local Storage**
   ```javascript
   // In browser console
   localStorage.setItem('google_maps_api_key', 'YOUR_API_KEY_HERE');
   ```

3. **Configure Map Provider**
   
   In `script.js`, modify the map initialization:
   ```javascript
   await mapProvider.initialize('map', center, 12, {
     provider: 'google', // Change from 'leaflet' to 'google'
   });
   ```

## Configuration

### Backend URL

The application automatically detects the backend URL. If you need to override it:

```javascript
// In api.js, modify the determineBaseURL method
determineBaseURL() {
  return 'http://your-backend-url:port';
}
```

### Map Styles

For Google Maps, you can customize the map style in `map.js`:

```javascript
getDefaultMapStyles() {
  return [
    // Your custom map styles
  ];
}
```

For Leaflet, you can change the tile provider:

```javascript
initializeLeaflet(containerId, center, zoom, options) {
  const tileUrl = 'https://your-tile-provider/{z}/{x}/{y}.png';
  // ...
}
```

## Development

### Building for Production

Currently, the frontend uses vanilla HTML/CSS/JavaScript and doesn't require a build step. For production:

1. Minify CSS and JavaScript files
2. Optimize images
3. Enable browser caching
4. Use a CDN for external libraries

### Testing

To test the application:

1. Start the backend server
2. Open the frontend in a browser
3. Test location search
4. Test route optimization
5. Test map controls
6. Test responsive design on different screen sizes

## Browser Support

- Chrome/Edge (recommended)
- Firefox
- Safari
- Mobile browsers (iOS Safari, Chrome Mobile)

## Troubleshooting

### Backend Connection Issues

- Ensure the Flask server is running
- Check that the backend URL is correct
- Verify CORS is enabled on the backend
- Check browser console for error messages

### Map Not Loading

- Check internet connection
- Verify map provider configuration
- Check browser console for API key errors
- Ensure external libraries (Leaflet/Google Maps) are loading

### Route Optimization Not Working

- Verify backend is responding correctly
- Check that source and destination are set
- Ensure coordinates are valid
- Check browser console for API errors

## API Integration

The frontend communicates with the backend through these endpoints:

- `GET /api/graph-bounds` - Get network bounds and info
- `GET /api/geocode?q={query}` - Search for locations
- `GET /api/congestion` - Get traffic congestion data
- `GET /api/city-insights` - Get city traffic insights
- `POST /api/optimize` - Calculate optimal routes

See `api.js` for the complete API service layer implementation.

## Performance Tips

- Use Google Maps for better performance in areas with good Google Maps coverage
- Enable traffic overlay sparingly as it requires additional API calls
- Clear routes between calculations to avoid memory leaks
- Use modern browsers for best performance

## Security Considerations

- Never commit API keys to version control
- Restrict Google Maps API keys to specific domains
- Use HTTPS in production
- Implement rate limiting on the backend
- Validate all user inputs

## License

This project is part of the Q-ROUTE Quantum-Inspired Traffic Route Optimizer.

## Support

For issues or questions, please refer to the main project documentation or contact the development team.
