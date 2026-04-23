import type {
	CartFormatResponse,
	BuyListItem,
	Card,
	CartFormatResponse as CartResponse,
	JobResponse,
	RecalculateResponse,
	VendorMeta,
} from './types';

const BASE = '/api';

async function post<T>(path: string, body: unknown): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
	});
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json();
}

async function get<T>(path: string): Promise<T> {
	const res = await fetch(`${BASE}${path}`);
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json();
}

export function getVendors(): Promise<VendorMeta[]> {
	return get('/vendors');
}

export function parseCards(cardList: string): Promise<Card[]> {
	return post('/parse', { card_list: cardList });
}

export function startScrape(
	cardList: string,
	enabledVendors: string[]
): Promise<{ job_id: string }> {
	return post('/scrape', { card_list: cardList, enabled_vendors: enabledVendors });
}

export function pollJob(jobId: string): Promise<JobResponse> {
	return get(`/jobs/${jobId}`);
}

export function openJobStream(jobId: string): EventSource {
	return new EventSource(`${BASE}/jobs/${jobId}/stream`);
}

export function recalculate(params: {
	job_id: string;
	selected_vendors: string[];
	vendor_weights: Record<string, number>;
	min_cards_per_vendor: number;
	consolidation_budget: number;
	pinned_printings?: Record<string, { set_code: string; collector_number: string; foil: boolean }>;
}): Promise<RecalculateResponse> {
	return post('/recalculate', params);
}

export function formatCart(
	storeName: string,
	buyList: BuyListItem[]
): Promise<CartFormatResponse> {
	return post('/cart/format', { store_name: storeName, buy_list: buyList });
}
