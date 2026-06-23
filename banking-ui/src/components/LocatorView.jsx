// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React, { useState, useEffect, useMemo } from 'react';
import { MapPin, Search, Navigation, Clock, Phone, ExternalLink } from 'lucide-react';
import { getLocations } from '../utils/api.js';
import GoogleCloudIcon from './GoogleCloudIcon.jsx';
import GcpInfoModal from './GcpInfoModal.jsx';

export default function LocatorView() {
  const [address, setAddress] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [locations, setLocations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gpsUsed, setGpsUsed] = useState(false);
  const [openOnly, setOpenOnly] = useState(false);
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  const projectId = window.firebaseConfig?.projectId;

  // Helper to determine if a location is open right now
  const isLocationOpen = (hours) => {
    if (!hours) return false;
    if (hours.toLowerCase() === "24/7") return true;

    const now = new Date();
    const day = now.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
    const [currHour, currMin] = timeStr.split(':').map(Number);
    const currTimeDecimal = currHour + currMin / 60;

    if (day >= 1 && day <= 5) {
      // Mon-Fri: 9am - 5pm
      return currTimeDecimal >= 9 && currTimeDecimal < 17;
    } else if (day === 6) {
      // Sat: 9am - 1pm
      return currTimeDecimal >= 9 && currTimeDecimal < 13;
    }
    return false;
  };

  const filteredLocations = useMemo(() => {
    if (!openOnly) return locations;
    return locations.filter(loc => isLocationOpen(loc.hours));
  }, [locations, openOnly]);

  const fetchByGPS = () => {
    if (!navigator.geolocation) {
      setError("Geolocation is not supported by your browser.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setGpsUsed(true);
    setAddress("");

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const data = await getLocations({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            type: typeFilter
          });
          setLocations(data.results || []);
        } catch (err) {
          console.error("Error fetching locations by GPS:", err);
          setError("Failed to find locations near you.");
        } finally {
          setIsLoading(false);
        }
      },
      (err) => {
        console.error("Geolocation error:", err);
        setError("Unable to retrieve your location. Please check browser permissions or search by address.");
        setIsLoading(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const handleSearchSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!address.trim()) return;

    setIsLoading(true);
    setError(null);
    setGpsUsed(false);

    try {
      const data = await getLocations({
        address: address.trim(),
        type: typeFilter
      });
      setLocations(data.results || []);
    } catch (err) {
      console.error("Error fetching locations by address:", err);
      setError("Failed to find locations. Please try again with a different address.");
    } finally {
      setIsLoading(false);
    }
  };

  // Re-fetch if filter changes and we already have some results
  useEffect(() => {
    if (gpsUsed) {
      fetchByGPS();
    } else if (address.trim()) {
      handleSearchSubmit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter]);

  return (
    <div className="max-w-7xl mx-auto pt-28 pb-12 px-6 min-h-screen flex flex-col animate-fade-in w-full">
      {/* Header */}
      <div className="w-full text-center space-y-3 mb-8 shrink-0 relative">
        <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-5xl">
          Find a Branch or ATM
        </h1>
        <p className="max-w-2xl mx-auto text-base text-slate-500 dark:text-slate-400">
          Locate your nearest bank branches and ATMs. Get directions, hours, contact info, and more.
        </p>
        <button
          onClick={() => setIsInfoModalOpen(true)}
          className="absolute right-0 top-1/2 -translate-y-1/2 p-2.5 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm"
          title="GCP App Integration Info"
        >
          <GoogleCloudIcon className="w-5 h-5" />
        </button>
      </div>

      {/* Main Section */}
      <div className="w-full flex flex-col gap-6 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl">
        
        {/* Controls Panel */}
        <div className="flex flex-col lg:flex-row gap-4 items-center justify-between">
          
          {/* Search Inputs */}
          <div className="flex-1 flex flex-col sm:flex-row gap-3 w-full lg:w-auto">
            <form onSubmit={handleSearchSubmit} className="relative flex-1">
              <Search className="absolute left-4 top-3.5 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="Enter city, state, address, or zip code"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="w-full pl-12 pr-4 py-3 rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 text-sm transition-all"
              />
              <button 
                type="submit" 
                className="absolute right-2.5 top-2 px-4 py-1.5 bg-slate-900 hover:bg-slate-800 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl transition-all cursor-pointer"
              >
                Search
              </button>
            </form>

            <button
              onClick={fetchByGPS}
              className="px-5 py-3 rounded-2xl bg-emerald-500 hover:bg-emerald-600 text-white font-medium text-sm flex items-center justify-center gap-2 cursor-pointer shadow-md hover:shadow-lg transition-all"
            >
              <Navigation className="w-4 h-4" />
              <span>Use Current Location</span>
            </button>
          </div>

          {/* Filters & Toggle */}
          <div className="flex flex-wrap items-center gap-4 w-full lg:w-auto justify-end">
            {/* Type Filters */}
            <div className="flex justify-end gap-1.5 bg-slate-100 dark:bg-slate-900 p-1.5 rounded-2xl h-[44px] items-center">
              {["ALL", "BRANCH", "ATM"].map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`px-4 py-1.5 text-xs font-bold rounded-xl transition-all cursor-pointer ${
                    typeFilter === t
                      ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  {t === "ALL" ? "All" : t === "BRANCH" ? "Branches" : "ATMs"}
                </button>
              ))}
            </div>

            {/* Open Now Toggle */}
            <label className="flex items-center gap-2.5 cursor-pointer select-none shrink-0 border border-slate-200 dark:border-slate-800 rounded-2xl px-4 py-2 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-855 transition-all h-[44px]">
              <div className="relative">
                <input
                  type="checkbox"
                  checked={openOnly}
                  onChange={(e) => setOpenOnly(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-8 h-4.5 bg-slate-200 dark:bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3.5 after:w-3.5 after:transition-all peer-checked:bg-emerald-500"></div>
              </div>
              <span className="text-xs font-bold text-slate-650 dark:text-slate-300">Open Now Only</span>
            </label>
          </div>

        </div>

        {/* Error Message */}
        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/50 rounded-2xl text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
            <span className="font-semibold">Error:</span> {error}
          </div>
        )}

        {/* Results grid */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Finding nearby branches and ATMs...</span>
          </div>
        ) : filteredLocations.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredLocations.map((loc) => (
              <div 
                key={loc.id} 
                className="flex flex-col justify-between p-6 bg-slate-50 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60 rounded-2xl hover:shadow-lg hover:border-slate-300 dark:hover:border-slate-700 transition-all group"
              >
                <div>
                  {/* Title & Distance */}
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`px-2.5 py-1 text-[10px] font-extrabold tracking-wider uppercase rounded-full ${
                        loc.type === "BRANCH"
                          ? "bg-teal-50 dark:bg-teal-950/40 text-teal-600 dark:text-teal-400 border border-teal-200/50 dark:border-teal-850"
                          : "bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-200/50 dark:border-indigo-850"
                      }`}>
                        {loc.type}
                      </span>
                      {isLocationOpen(loc.hours) ? (
                        <span className="px-2 py-0.5 text-[9px] font-extrabold rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-250/30 dark:border-emerald-900/40 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                          Open Now
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[9px] font-extrabold rounded-full bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-450 border border-rose-250/30 dark:border-rose-900/40 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
                          Closed
                        </span>
                      )}
                    </div>
                    {loc.distance_miles !== null && (
                      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5 text-emerald-500" />
                        {loc.distance_miles} mi
                      </span>
                    )}
                  </div>

                  <h3 className="text-base font-bold text-slate-800 dark:text-slate-200 group-hover:text-emerald-500 transition-colors mb-2">
                    {loc.name}
                  </h3>

                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-4 leading-relaxed">
                    {loc.address}
                  </p>

                  {/* Details (hours, phone) */}
                  <div className="space-y-2 border-t border-slate-200/40 dark:border-slate-800/40 pt-4 text-xs text-slate-650 dark:text-slate-400">
                    {loc.hours && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span>{loc.hours}</span>
                      </div>
                    )}
                    {loc.phone_number && (
                      <div className="flex items-center gap-2">
                        <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span>{loc.phone_number}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Bottom Actions */}
                <div className="mt-6 pt-4 border-t border-slate-200/40 dark:border-slate-800/40">
                  <a
                    href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc.name + " " + loc.address)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-full py-2.5 rounded-xl border border-slate-205 hover:border-emerald-550 dark:border-slate-800 dark:hover:border-emerald-550 text-xs font-bold text-slate-700 dark:text-slate-300 hover:text-emerald-500 dark:hover:text-emerald-400 bg-white dark:bg-slate-900 hover:bg-slate-50/50 dark:hover:bg-slate-900/80 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    <span>Get Directions</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl text-slate-400 dark:text-slate-600 gap-3">
            <MapPin className="w-8 h-8 opacity-30 animate-pulse text-slate-400" />
            <div className="text-center space-y-1">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">No branches or ATMs displayed</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-xs mx-auto">
                Use your current location or search for an address, city, or zip code above to locate facilities.
              </p>
            </div>
          </div>
        )}

      </div>

      <GcpInfoModal
        isOpen={isInfoModalOpen}
        onClose={() => setIsInfoModalOpen(false)}
        title="BigQuery Database Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            This branch and ATM locator search is powered by <strong>Google Cloud Platform's BigQuery</strong> serverless data warehouse.
          </p>
          <p>
            The backend retrieves retail location coordinates and service types in real-time by querying geographic distance metrics from the locations table.
          </p>
          <p>
            You can inspect the underlying dataset schema and query logs directly in the Google Cloud Console using the link below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">BigQuery Locations Table</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">View schemas, columns, preview rows, and execute query analysis.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/bigquery?project=${projectId}&ws=!1m6!1m5!4m3!1s${projectId}!2sbanking!3sretail_location!23sRESOURCE_LIST`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Table</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>
    </div>
  );
}
