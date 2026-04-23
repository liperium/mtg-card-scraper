import { writable, derived } from 'svelte/store';
import type { JobResponse, PinnedPrinting, RecalculateResponse, VendorMeta } from './types';

// Vendor metadata (loaded on mount)
export const vendors = writable<VendorMeta[]>([]);

// Card input
export const cardList = writable('');

// Vendor selection for scraping
export const enabledVendors = writable<Set<string>>(new Set());

// Active scrape job
export const currentJobId = writable<string | null>(null);
export const jobState = writable<JobResponse | null>(null);
export const vendorProgress = writable<Record<string, string>>({});

// Vendor selection for recalculate (post-scrape)
export const selectedVendors = writable<Set<string>>(new Set());
export const vendorWeights = writable<Record<string, number>>({});
export const minCardsPerVendor = writable(1);
export const consolidationBudget = writable(0);

// Pinned printings (card name → printing override)
export const pinnedPrintings = writable<Record<string, PinnedPrinting>>({});

// Recalculate results
export const results = writable<RecalculateResponse | null>(null);

// UI state
export type AppPhase = 'input' | 'scraping' | 'results';
export const phase = writable<AppPhase>('input');
export const error = writable<string | null>(null);

// Derived: grand total across all vendors
export const grandTotal = derived(results, ($results) => {
	if (!$results) return null;
	return Object.values($results.summary).reduce(
		(sum, s) => sum + s.effective_total,
		0
	);
});
