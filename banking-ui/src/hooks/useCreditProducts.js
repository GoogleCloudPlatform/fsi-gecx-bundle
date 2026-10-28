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

import { useEffect, useCallback, useSyncExternalStore } from 'react';
import {
  subscribeCreditProducts,
  getCreditProductsSnapshot,
  fetchCreditProducts,
  resolveCreditProduct,
  buildCardApplicationPayload,
} from '../utils/creditProducts.js';

/**
 * Hook providing credit product catalog data with shared module-level caching and retry.
 * Returns { products, loading, error, retry }
 */
export function useCreditProducts() {
  const snapshot = useSyncExternalStore(
    subscribeCreditProducts,
    getCreditProductsSnapshot,
    getCreditProductsSnapshot
  );

  useEffect(() => {
    // If not loaded yet, initiate fetch on mount
    if (snapshot.products.length === 0) {
      fetchCreditProducts().catch(() => {});
    }
  }, [snapshot.products.length]);

  const retry = useCallback(() => {
    return fetchCreditProducts(true).catch(() => {});
  }, []);

  return {
    products: snapshot.products,
    loading: snapshot.loading,
    error: snapshot.error,
    retry,
  };
}

export {
  useCreditProducts as default,
  resolveCreditProduct,
  buildCardApplicationPayload,
};
