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

import { useEffect, useSyncExternalStore } from 'react';
import { getCreditProducts } from './api.js';

let productsFetcher = getCreditProducts;

export function setCreditProductsFetcher(fetcher) {
  productsFetcher = fetcher || getCreditProducts;
}

export function resetCreditProductsFetcher() {
  productsFetcher = getCreditProducts;
}

let store = {
  products: [],
  loading: true,
  error: null,
};
let inFlightPromise = null;
const listeners = new Set();

function notify() {
  listeners.forEach((listener) => {
    try {
      listener();
    } catch (err) {
      console.error('Error in credit products listener:', err);
    }
  });
}

export function subscribeCreditProducts(listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getCreditProductsSnapshot() {
  return store;
}

export async function fetchCreditProducts(force = false) {
  if (store.products.length > 0 && !force && !store.error) {
    return store.products;
  }
  if (inFlightPromise) {
    return inFlightPromise;
  }
  store = { ...store, loading: true, error: null };
  notify();

  inFlightPromise = productsFetcher()
    .then((data) => {
      const products = data?.products || [];
      store = { products, loading: false, error: null };
      inFlightPromise = null;
      notify();
      return products;
    })
    .catch((err) => {
      store = { products: [], loading: false, error: err };
      inFlightPromise = null;
      notify();
      throw err;
    });

  return inFlightPromise;
}

export function resetCreditProductsCache() {
  store = { products: [], loading: true, error: null };
  inFlightPromise = null;
  notify();
}

/**
 * Hook providing credit product catalog data with shared module-level caching.
 * Returns { products, loading, error }
 */
export function useCreditProducts() {
  useEffect(() => {
    if (store.products.length === 0 && !inFlightPromise && !store.error) {
      fetchCreditProducts().catch(() => {});
    }
  }, []);

  return useSyncExternalStore(
    subscribeCreditProducts,
    getCreditProductsSnapshot,
    getCreditProductsSnapshot
  );
}

/**
 * Resolves a credit product from the catalog by value matching:
 * 1. product_code (case-insensitive, exact or hyphen/underscore normalized)
 * 2. product_name (case-insensitive)
 * Returns the matching product or null.
 */
export function resolveCreditProduct(products, value) {
  if (!Array.isArray(products) || !value || typeof value !== 'string') {
    return null;
  }
  const query = value.trim().toLowerCase();
  if (!query) {
    return null;
  }

  // 1. Match product_code (case-insensitive)
  const byCode = products.find(
    (p) => p && typeof p.product_code === 'string' && p.product_code.toLowerCase() === query
  );
  if (byCode) {
    return byCode;
  }

  // 1b. Tolerate hyphenated product code (e.g. "cashback-everyday" vs "CASHBACK_EVERYDAY")
  const normalizedQuery = query.replace(/-/g, '_');
  const byCodeNormalized = products.find(
    (p) => p && typeof p.product_code === 'string' && p.product_code.toLowerCase() === normalizedQuery
  );
  if (byCodeNormalized) {
    return byCodeNormalized;
  }

  // 2. Match product_name (case-insensitive)
  const byName = products.find(
    (p) => p && typeof p.product_name === 'string' && p.product_name.trim().toLowerCase() === query
  );
  if (byName) {
    return byName;
  }

  return null;
}

/**
 * Constructs the application creation payload for credit card products.
 */
export function buildCardApplicationPayload(productCode, requestedAmount) {
  return {
    product_category: 'CARD',
    product_type: productCode,
    requested_amount: Number(requestedAmount),
  };
}
