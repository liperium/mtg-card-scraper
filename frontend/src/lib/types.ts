export interface VendorMeta {
	name: string;
	shipping_cost: number;
	fulfillment_label: string;
	supports_bulk_add: boolean;
	deck_builder_url: string;
	supports_set_info: boolean;
	supports_foil: boolean;
}

export interface Card {
	quantity: number;
	name: string;
	set_code: string | null;
	collector_number: string | null;
}

export interface CardPrice {
	card_name: string;
	original_query: string;
	price: number | null;
	website: string;
	found: boolean;
	quantity_available: number;
	set_code: string | null;
	collector_number: string | null;
	foil: boolean;
}

export type JobStatus = 'pending' | 'running' | 'complete' | 'error';

export interface JobResponse {
	job_id: string;
	status: JobStatus;
	vendor_progress: Record<string, string>;
	raw_vendor_results: Record<string, CardPrice[]> | null;
	parsed_cards: Card[] | null;
	error: string | null;
}

export interface BestPriceEntry {
	quantity_needed: number;
	best_price: number | null;
	website: string;
	quantity_available: number;
}

export interface BuyListItem {
	card: string;
	quantity: number;
	price_per_unit: number;
	total_price: number;
}

export interface VendorSummary {
	total_cards: number;
	total_price: number;
	shipping_cost: number;
	effective_total: number;
}

export interface RecalculateResponse {
	best_prices: Record<string, BestPriceEntry>;
	buy_lists: Record<string, BuyListItem[]>;
	summary: Record<string, VendorSummary>;
	not_found: string[];
	warnings: string[];
}

export interface CartFormatResponse {
	url: string;
	card_list: string;
	supports_bulk_add: boolean;
}

export interface SSEDoneEvent {
	done: true;
	status: JobStatus;
}

export interface SSEVendorEvent {
	vendor: string;
	status: string;
}
