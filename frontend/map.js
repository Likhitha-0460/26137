/**
 * Map Provider Abstraction Layer
 * Supports both Google Maps and Leaflet with automatic fallback
 */

class MapProvider {
  constructor() {
    this.provider = null;
    this.map = null;
    this.markers = [];
    this.polylines = [];
    this.heatmapLayers = [];
  }

  async initialize(containerId, center, zoom, options = {}) {
    const googleApiKey = this.getGoogleMapsApiKey();
    
    if (googleApiKey && options.provider !== 'leaflet') {
      return this.initializeGoogleMaps(containerId, center, zoom, googleApiKey, options);
    } else {
      return this.initializeLeaflet(containerId, center, zoom, options);
    }
  }

  getGoogleMapsApiKey() {
    // Check for API key in multiple locations
    return (
      window.GOOGLE_MAPS_API_KEY || 
      document.querySelector('meta[name="google-maps-api-key"]')?.content ||
      localStorage.getItem('google_maps_api_key') ||
      null
    );
  }

  async initializeGoogleMaps(containerId, center, zoom, apiKey, options) {
    if (!window.google || !window.google.maps) {
      await this.loadGoogleMapsScript(apiKey);
    }

    this.provider = 'google';
    const { provider, ...mapOptions } = options;
    
    const googleMapOptions = {
      center: { lat: center[0], lng: center[1] },
      zoom: zoom,
      styles: mapOptions.mapStyles || this.getDefaultMapStyles(),
      disableDefaultUI: false,
      zoomControl: true,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: mapOptions.fullscreenControl !== false,
      ...mapOptions
    };

    this.map = new google.maps.Map(document.getElementById(containerId), googleMapOptions);
    return this.map;
  }

  async loadGoogleMapsScript(apiKey) {
    return new Promise((resolve, reject) => {
      if (window.google && window.google.maps) {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  initializeLeaflet(containerId, center, zoom, options) {
    this.provider = 'leaflet';
    
    // Import Leaflet if not available
    if (typeof L === 'undefined') {
      console.error('Leaflet not loaded. Please include Leaflet CSS and JS.');
      return null;
    }

    this.map = L.map(containerId, {
      zoomControl: options.zoomControl !== false,
      ...options
    }).setView(center, zoom);

    // Add tile layer
    const tileUrl = options.tileUrl || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    const attribution = options.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
    
    L.tileLayer(tileUrl, {
      attribution: attribution,
      maxZoom: 19,
      ...options.tileOptions
    }).addTo(this.map);

    return this.map;
  }

  getDefaultMapStyles() {
    // Clean, light map style similar to Google Maps
    return [
      {
        "featureType": "water",
        "elementType": "geometry",
        "stylers": [{ "color": "#e9e9e9" }, { "lightness": 17 }]
      },
      {
        "featureType": "landscape",
        "elementType": "geometry",
        "stylers": [{ "color": "#f5f5f5" }, { "lightness": 20 }]
      },
      {
        "featureType": "road.highway",
        "elementType": "geometry",
        "stylers": [{ "color": "#ffffff" }, { "lightness": 17 }]
      },
      {
        "featureType": "road.arterial",
        "elementType": "geometry",
        "stylers": [{ "color": "#ffffff" }, { "lightness": 18 }]
      },
      {
        "featureType": "road.local",
        "elementType": "geometry",
        "stylers": [{ "color": "#ffffff" }, { "lightness": 16 }]
      },
      {
        "featureType": "poi",
        "elementType": "geometry",
        "stylers": [{ "color": "#f5f5f5" }, { "lightness": 21 }]
      },
      {
        "featureType": "poi.park",
        "elementType": "geometry",
        "stylers": [{ "color": "#dedede" }, { "lightness": 21 }]
      }
    ];
  }

  // Marker methods
  addMarker(position, options = {}) {
    if (this.provider === 'google') {
      const marker = new google.maps.Marker({
        position: { lat: position[0], lng: position[1] },
        ...options
      });
      marker.setMap(this.map);
      this.markers.push(marker);
      return marker;
    } else {
      const marker = L.marker(position, options).addTo(this.map);
      this.markers.push(marker);
      return marker;
    }
  }

  removeMarker(marker) {
    if (this.provider === 'google') {
      marker.setMap(null);
    } else {
      this.map.removeLayer(marker);
    }
    this.markers = this.markers.filter(m => m !== marker);
  }

  clearMarkers() {
    this.markers.forEach(marker => this.removeMarker(marker));
    this.markers = [];
  }

  // Polyline methods
  addPolyline(latlngs, options = {}) {
    if (this.provider === 'google') {
      const path = latlngs.map(ll => ({ lat: ll[0], lng: ll[1] }));
      const polyline = new google.maps.Polyline({
        path: path,
        ...options
      });
      polyline.setMap(this.map);
      this.polylines.push(polyline);
      return polyline;
    } else {
      const polyline = L.polyline(latlngs, options).addTo(this.map);
      this.polylines.push(polyline);
      return polyline;
    }
  }

  removePolyline(polyline) {
    if (this.provider === 'google') {
      polyline.setMap(null);
    } else {
      this.map.removeLayer(polyline);
    }
    this.polylines = this.polylines.filter(p => p !== polyline);
  }

  clearPolylines() {
    this.polylines.forEach(polyline => this.removePolyline(polyline));
    this.polylines = [];
  }

  // Heatmap/Traffic overlay methods
  addTrafficOverlay(edges, options = {}) {
    this.clearTrafficOverlay();
    
    edges.forEach(edge => {
      const from = [edge.from.lat, edge.from.lon];
      const to = [edge.to.lat, edge.to.lon];
      const color = this.getCongestionColor(edge.congestion);
      
      if (this.provider === 'google') {
        const polyline = new google.maps.Polyline({
          path: [
            { lat: from[0], lng: from[1] },
            { lat: to[0], lng: to[1] }
          ],
          strokeColor: color,
          strokeWeight: options.weight || 3,
          strokeOpacity: options.opacity || 0.6,
          ...options
        });
        polyline.setMap(this.map);
        this.heatmapLayers.push(polyline);
      } else {
        const polyline = L.polyline([from, to], {
          color: color,
          weight: options.weight || 3,
          opacity: options.opacity || 0.6,
          ...options
        }).addTo(this.map);
        this.heatmapLayers.push(polyline);
      }
    });
  }

  clearTrafficOverlay() {
    this.heatmapLayers.forEach(layer => {
      if (this.provider === 'google') {
        layer.setMap(null);
      } else {
        this.map.removeLayer(layer);
      }
    });
    this.heatmapLayers = [];
  }

  getCongestionColor(congestion) {
    if (congestion > 2.2) return '#ef4444'; // Red - severe
    if (congestion > 1.6) return '#f59e0b'; // Orange - moderate
    return '#22c55e'; // Green - low
  }

  // Map control methods
  setCenter(center, zoom) {
    if (this.provider === 'google') {
      this.map.setCenter({ lat: center[0], lng: center[1] });
      if (zoom !== undefined) this.map.setZoom(zoom);
    } else {
      if (zoom !== undefined) {
        this.map.setView(center, zoom);
      } else {
        this.map.panTo(center);
      }
    }
  }

  fitBounds(bounds, padding = {}) {
    if (this.provider === 'google') {
      const googleBounds = new google.maps.LatLngBounds();
      bounds.forEach(bound => {
        googleBounds.extend({ lat: bound[0], lng: bound[1] });
      });
      this.map.fitBounds(googleBounds, padding);
    } else {
      const leafletBounds = L.latLngBounds(bounds);
      this.map.fitBounds(leafletBounds, padding);
    }
  }

  getCenter() {
    if (this.provider === 'google') {
      const center = this.map.getCenter();
      return [center.lat(), center.lng()];
    } else {
      const center = this.map.getCenter();
      return [center.lat, center.lng];
    }
  }

  getZoom() {
    return this.map.getZoom();
  }

  // Event handlers
  on(event, handler) {
    if (this.provider === 'google') {
      this.map.addListener(event, handler);
    } else {
      this.map.on(event, handler);
    }
  }

  off(event, handler) {
    if (this.provider === 'google') {
      google.maps.event.removeListener(this.map, event, handler);
    } else {
      this.map.off(event, handler);
    }
  }

  // Cleanup
  destroy() {
    this.clearMarkers();
    this.clearPolylines();
    this.clearTrafficOverlay();
    this.map = null;
    this.provider = null;
  }

  // Get provider type
  getProvider() {
    return this.provider;
  }
}

// Create global instance
const mapProvider = new MapProvider();
