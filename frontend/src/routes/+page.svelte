<script lang="ts">
	import { onMount } from 'svelte';
	import {
		formatCart,
		getVendors,
		openJobStream,
		pollJob,
		recalculate,
		startScrape,
	} from '$lib/api';
	import {
		cardList,
		consolidationBudget,
		enabledVendors,
		error,
		grandTotal,
		jobState,
		minCardsPerVendor,
		phase,
		results,
		selectedVendors,
		vendorProgress,
		vendorWeights,
		vendors,
	} from '$lib/stores';
	import type { BuyListItem } from '$lib/types';

	// -------------------------------------------------------------------------
	// Init
	// -------------------------------------------------------------------------
	onMount(async () => {
		try {
			const v = await getVendors();
			vendors.set(v);
			enabledVendors.set(new Set(v.map((x) => x.name)));
			selectedVendors.set(new Set(v.map((x) => x.name)));
			vendorWeights.set(Object.fromEntries(v.map((x) => [x.name, 1.0])));
		} catch (e) {
			error.set('Failed to load vendors. Is the backend running?');
		}
	});

	// -------------------------------------------------------------------------
	// Scrape
	// -------------------------------------------------------------------------
	let scrapeInProgress = false;
	let recalcTimer: ReturnType<typeof setTimeout> | null = null;

	async function handleScrape() {
		if (!$cardList.trim()) return;

		error.set(null);
		vendorProgress.set({});
		jobState.set(null);
		results.set(null);
		phase.set('scraping');
		scrapeInProgress = true;

		try {
			const { job_id } = await startScrape($cardList, [...$enabledVendors]);

			// Listen to SSE for live vendor status
			const es = openJobStream(job_id);
			es.onmessage = (event) => {
				const data = JSON.parse(event.data);
				if (data.vendor) {
					vendorProgress.update((p) => ({ ...p, [data.vendor]: data.status }));
				}
				if (data.done) {
					es.close();
					// Fetch final job state then trigger first recalculate
					pollJob(job_id).then((job) => {
						jobState.set(job);
						selectedVendors.set(new Set(Object.keys(job.raw_vendor_results ?? {})));
						triggerRecalculate(job_id);
					});
				}
			};
			es.onerror = () => {
				es.close();
				// Fallback poll
				pollJob(job_id).then((job) => {
					jobState.set(job);
					if (job.status === 'complete') {
						selectedVendors.set(new Set(Object.keys(job.raw_vendor_results ?? {})));
						triggerRecalculate(job_id);
					} else if (job.status === 'error') {
						error.set(job.error ?? 'Scrape failed');
						phase.set('input');
						scrapeInProgress = false;
					}
				});
			};
		} catch (e: any) {
			error.set(e?.message ?? 'Failed to start scrape');
			phase.set('input');
			scrapeInProgress = false;
		}
	}

	// -------------------------------------------------------------------------
	// Recalculate (debounced)
	// -------------------------------------------------------------------------
	function triggerRecalculate(jobId?: string) {
		if (recalcTimer) clearTimeout(recalcTimer);
		recalcTimer = setTimeout(() => doRecalculate(jobId), 300);
	}

	async function doRecalculate(jobId?: string) {
		const id = jobId ?? $jobState?.job_id;
		if (!id) return;

		try {
			const res = await recalculate({
				job_id: id,
				selected_vendors: [...$selectedVendors],
				vendor_weights: $vendorWeights,
				min_cards_per_vendor: $minCardsPerVendor,
				consolidation_budget: $consolidationBudget,
			});
			results.set(res);
			phase.set('results');
			scrapeInProgress = false;
		} catch (e: any) {
			error.set(e?.message ?? 'Recalculate failed');
		}
	}

	// React to filter changes
	$: if ($jobState?.status === 'complete') {
		triggerRecalculate();
	}

	// -------------------------------------------------------------------------
	// Cart
	// -------------------------------------------------------------------------
	async function openCart(storeName: string, buyList: BuyListItem[]) {
		try {
			const { url, card_list } = await formatCart(storeName, buyList);
			await navigator.clipboard.writeText(card_list).catch(() => {});
			window.open(url, '_blank');
		} catch (e: any) {
			error.set(e?.message ?? 'Failed to open cart');
		}
	}

	// -------------------------------------------------------------------------
	// Debug panel
	// -------------------------------------------------------------------------
	let debugOpen = false;

	// Pivot: card name → vendor → CardPrice
	$: debugTable = (() => {
		const raw = $jobState?.raw_vendor_results;
		if (!raw) return null;
		const vendorNames = Object.keys(raw);
		// Collect all unique card names (by original_query)
		const cardSet = new Set<string>();
		for (const prices of Object.values(raw)) {
			for (const p of prices) cardSet.add(p.original_query);
		}
		const cards = [...cardSet].sort();
		// Build lookup: vendor → card_name → CardPrice
		const lookup: Record<string, Record<string, import('$lib/types').CardPrice>> = {};
		for (const [vendor, prices] of Object.entries(raw)) {
			lookup[vendor] = {};
			for (const p of prices) {
				lookup[vendor][p.original_query] = p;
			}
		}
		return { vendorNames, cards, lookup };
	})();

	// -------------------------------------------------------------------------
	// Helpers
	// -------------------------------------------------------------------------
	function vendorStatusIcon(status: string): string {
		if (status === 'complete') return '✓';
		if (status === 'error') return '✗';
		if (status === 'loading') return '⟳';
		return '…';
	}

	function vendorStatusClass(status: string): string {
		if (status === 'complete') return 'status-ok';
		if (status === 'error') return 'status-err';
		return 'status-loading';
	}

	function fmt(n: number | null | undefined): string {
		if (n == null) return 'N/A';
		return `$${n.toFixed(2)}`;
	}


</script>

<main>
	<header>
		<h1>MTG Price Finder</h1>
		<p class="subtitle">Find the cheapest split across Canadian stores</p>
	</header>

	{#if $error}
		<div class="alert-error">{$error} <button on:click={() => error.set(null)}>✕</button></div>
	{/if}

	<!-- ====================================================================== -->
	<!-- INPUT PHASE                                                             -->
	<!-- ====================================================================== -->
	{#if $phase === 'input' || $phase === 'scraping'}
		<section class="card">
			<h2>Card List</h2>
			<textarea
				bind:value={$cardList}
				placeholder="Paste Moxfield list here…
1 Lightning Bolt (2XM) 141
1 Sol Ring (CMM) 396"
				rows="10"
				disabled={$phase === 'scraping'}
			></textarea>

			<div class="vendor-grid">
				{#each $vendors as v}
					<label class="vendor-toggle" class:checked={$enabledVendors.has(v.name)}>
						<input
							type="checkbox"
							checked={$enabledVendors.has(v.name)}
							disabled={$phase === 'scraping'}
							on:change={() => {
								enabledVendors.update((s) => {
									const next = new Set(s);
									next.has(v.name) ? next.delete(v.name) : next.add(v.name);
									return next;
								});
							}}
						/>
						{v.name}
						<span class="ship-label">{v.fulfillment_label}</span>
					</label>
				{/each}
			</div>

			<button
				class="btn-primary"
				on:click={handleScrape}
				disabled={$phase === 'scraping' || !$cardList.trim() || $enabledVendors.size === 0}
			>
				{$phase === 'scraping' ? 'Searching…' : 'Find Best Prices'}
			</button>
		</section>

		<!-- Live vendor progress -->
		{#if $phase === 'scraping'}
			<section class="card">
				<h2>Scraping…</h2>
				<div class="progress-grid">
					{#each $vendors.filter((v) => $enabledVendors.has(v.name)) as v}
						{@const status = $vendorProgress[v.name] ?? 'pending'}
						<div class="progress-row {vendorStatusClass(status)}">
							<span class="icon">{vendorStatusIcon(status)}</span>
							<span>{v.name}</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}
	{/if}

	<!-- ====================================================================== -->
	<!-- RESULTS PHASE                                                           -->
	<!-- ====================================================================== -->
	{#if $phase === 'results' && $results}
		<div class="results-layout">
			<!-- Sidebar: filters -->
			<aside class="card sidebar">
				<h2>Filters</h2>

				<button class="btn-secondary full-width" on:click={() => phase.set('input')}>
					← New Search
				</button>

				<div class="filter-group">
					<label class="filter-label">Vendors</label>
					{#each $vendors.filter((v) => Object.keys($jobState?.raw_vendor_results ?? {}).includes(v.name)) as v}
						<label class="vendor-toggle small" class:checked={$selectedVendors.has(v.name)}>
							<input
								type="checkbox"
								checked={$selectedVendors.has(v.name)}
								on:change={() => {
									selectedVendors.update((s) => {
										const next = new Set(s);
										next.has(v.name) ? next.delete(v.name) : next.add(v.name);
										return next;
									});
									triggerRecalculate();
								}}
							/>
							{v.name}
						</label>
					{/each}
				</div>

				<div class="filter-group">
					<label class="filter-label">Vendor Weights</label>
					{#each $vendors.filter((v) => $selectedVendors.has(v.name)) as v}
						<div class="weight-row">
							<span>{v.name}</span>
							<select
								value={$vendorWeights[v.name] ?? 1.0}
								on:change={(e) => {
									vendorWeights.update((w) => ({
										...w,
										[v.name]: parseFloat((e.target as HTMLSelectElement).value),
									}));
									triggerRecalculate();
								}}
							>
								<option value={0.85}>Preferred (×0.85)</option>
								<option value={1.0}>Normal (×1.0)</option>
								<option value={1.2}>Deprioritized (×1.2)</option>
							</select>
						</div>
					{/each}
				</div>

				<div class="filter-group">
					<label class="filter-label">Min cards/store: {$minCardsPerVendor}</label>
					<input
						type="range"
						min="1"
						max="10"
						bind:value={$minCardsPerVendor}
						on:change={() => triggerRecalculate()}
					/>
				</div>

				<div class="filter-group">
					<label class="filter-label">Consolidation budget: {fmt($consolidationBudget)}</label>
					<input
						type="range"
						min="0"
						max="20"
						step="0.5"
						bind:value={$consolidationBudget}
						on:change={() => triggerRecalculate()}
					/>
				</div>
			</aside>

			<!-- Main results -->
			<div class="results-main">
				<!-- Summary -->
				<section class="card">
					<h2>Summary</h2>
					<div class="summary-grid">
						{#each Object.entries($results.summary) as [vendor, s]}
							{@const vendorWarning = $results.warnings.find((w) => w.includes(vendor)) ?? null}
							<div class="summary-card" class:has-warning={vendorWarning}>
								{#if vendorWarning}
									<div class="warn-icon" title={vendorWarning}>⚠</div>
								{/if}
								<div class="summary-vendor">{vendor}</div>
								<div class="summary-count">{s.total_cards} cards</div>
								<div class="summary-price">{fmt(s.total_price)}</div>
								{#if s.shipping_cost > 0}
									<div class="summary-shipping">+ {fmt(s.shipping_cost)} shipping</div>
									<div class="summary-total">{fmt(s.effective_total)} total</div>
								{/if}
								<button
									class="btn-cart"
									on:click={() => openCart(vendor, $results!.buy_lists[vendor] ?? [])}
								>
									Open Cart
								</button>
							</div>
						{/each}
					</div>
					{#if $grandTotal != null}
						<div class="grand-total">Grand total: {fmt($grandTotal)}</div>
					{/if}
				</section>

				<!-- Best prices table -->
				<section class="card">
					<h2>Best Prices per Card</h2>
					<table>
						<thead>
							<tr>
								<th>Card</th>
								<th>Qty</th>
								<th>Price</th>
								<th>Store</th>
								<th>In Stock</th>
							</tr>
						</thead>
						<tbody>
							{#each Object.entries($results.best_prices) as [card, info]}
								<tr>
									<td>{card}</td>
									<td>{info.quantity_needed}</td>
									<td>{fmt(info.best_price)}</td>
									<td>{info.website}</td>
									<td>{info.quantity_available}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</section>

				<!-- Buy lists per vendor -->
				{#each Object.entries($results.buy_lists) as [vendor, items]}
					<section class="card">
						<div class="buy-list-header">
							<h2>{vendor}</h2>
							<button class="btn-cart" on:click={() => openCart(vendor, items)}>
								Open Cart
							</button>
						</div>
						<table>
							<thead>
								<tr>
									<th>Card</th>
									<th>Qty</th>
									<th>Unit</th>
									<th>Total</th>
								</tr>
							</thead>
							<tbody>
								{#each items as item}
									<tr>
										<td>{item.card}</td>
										<td>{item.quantity}</td>
										<td>{fmt(item.price_per_unit)}</td>
										<td>{fmt(item.total_price)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</section>
				{/each}

				<!-- Not found -->
				{#if $results.not_found.length > 0}
					<section class="card">
						<h2>Not Found ({$results.not_found.length})</h2>
						<ul class="not-found-list">
							{#each $results.not_found as card}
								<li>{card}</li>
							{/each}
						</ul>
					</section>
				{/if}

				<!-- Debug panel -->
				{#if debugTable}
					<section class="card debug-section">
						<button
							class="debug-toggle"
							on:click={() => (debugOpen = !debugOpen)}
							aria-expanded={debugOpen}
						>
							<span class="debug-chevron" class:open={debugOpen}>▶</span>
							Raw prices per vendor
						</button>

						{#if debugOpen}
							<div class="debug-scroll">
								<table class="debug-table">
									<thead>
										<tr>
											<th class="debug-card-col">Card</th>
											{#each debugTable.vendorNames as vendor}
												<th>{vendor}</th>
											{/each}
										</tr>
									</thead>
									<tbody>
										{#each debugTable.cards as card}
											<tr>
												<td class="debug-card-col">{card}</td>
												{#each debugTable.vendorNames as vendor}
													{@const p = debugTable.lookup[vendor]?.[card]}
													<td class:debug-found={p?.found} class:debug-notfound={!p?.found}>
														{#if p?.found && p.price != null}
															{fmt(p.price)}
															{#if p.quantity_available > 0}
																<span class="debug-qty">({p.quantity_available})</span>
															{/if}
														{:else}
															<span class="debug-na">—</span>
														{/if}
													</td>
												{/each}
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</section>
				{/if}
			</div>
		</div>
	{/if}
</main>

<style>
	main {
		max-width: 1200px;
		margin: 0 auto;
		padding: 2rem 1rem;
	}

	header {
		margin-bottom: 2rem;
	}

	h1 {
		margin: 0 0 0.25rem;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--accent);
	}

	h2 {
		margin: 0 0 1rem;
		font-size: 1.1rem;
		font-weight: 600;
	}

	.subtitle {
		margin: 0;
		color: var(--text-muted);
	}

	.card {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 1.25rem;
		margin-bottom: 1rem;
	}

	.alert-error {
		background: #3a1515;
		border: 1px solid var(--error);
		border-radius: var(--radius);
		padding: 0.75rem 1rem;
		margin-bottom: 1rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
		color: #ffcccc;
	}

	.alert-error button {
		background: none;
		border: none;
		color: inherit;
		font-size: 1rem;
		padding: 0;
	}

	textarea {
		width: 100%;
		background: var(--surface2);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		padding: 0.75rem;
		resize: vertical;
		margin-bottom: 1rem;
	}

	.vendor-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.vendor-toggle {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 0.75rem;
		background: var(--surface2);
		border: 1px solid var(--border);
		border-radius: 20px;
		cursor: pointer;
		user-select: none;
		transition: border-color 0.15s;
	}

	.vendor-toggle.checked {
		border-color: var(--accent);
		color: var(--accent);
	}

	.vendor-toggle.small {
		font-size: 0.85rem;
		padding: 0.3rem 0.6rem;
	}

	.vendor-toggle input {
		display: none;
	}

	.ship-label {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.btn-primary {
		background: var(--accent);
		color: white;
		border: none;
		border-radius: var(--radius);
		padding: 0.65rem 1.5rem;
		font-size: 0.95rem;
		font-weight: 600;
		transition: background 0.15s;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-secondary {
		background: var(--surface2);
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
	}

	.btn-secondary:hover {
		border-color: var(--accent);
	}

	.full-width {
		width: 100%;
		margin-bottom: 1rem;
	}

	.btn-cart {
		background: var(--success);
		color: white;
		border: none;
		border-radius: var(--radius);
		padding: 0.4rem 0.9rem;
		font-size: 0.85rem;
		font-weight: 600;
	}

	.btn-cart:hover {
		opacity: 0.85;
	}

	/* Progress */
	.progress-grid {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.progress-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.4rem 0.75rem;
		border-radius: var(--radius);
		background: var(--surface2);
	}

	.status-ok { color: var(--success); }
	.status-err { color: var(--error); }
	.status-loading { color: var(--warning); }

	.icon {
		font-size: 1rem;
		width: 1.2rem;
		text-align: center;
	}

	/* Results layout */
	.results-layout {
		display: grid;
		grid-template-columns: 260px 1fr;
		gap: 1rem;
		align-items: start;
	}

	@media (max-width: 768px) {
		.results-layout {
			grid-template-columns: 1fr;
		}
	}

	.sidebar {
		position: sticky;
		top: 1rem;
	}

	.filter-group {
		margin-bottom: 1.25rem;
	}

	.filter-label {
		display: block;
		font-size: 0.8rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.5rem;
	}

	.weight-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.4rem;
		font-size: 0.85rem;
	}

	.weight-row select {
		background: var(--surface2);
		border: 1px solid var(--border);
		border-radius: 4px;
		color: var(--text);
		padding: 0.2rem 0.4rem;
		font-size: 0.8rem;
	}

	input[type='range'] {
		width: 100%;
		accent-color: var(--accent);
	}

	/* Summary */
	.summary-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.summary-card {
		position: relative;
		background: var(--surface2);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.summary-vendor {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.summary-count {
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	.summary-price {
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--accent);
	}

	.summary-shipping, .summary-total {
		font-size: 0.8rem;
		color: var(--text-muted);
	}

	.summary-total {
		color: var(--text);
		font-weight: 600;
	}

	.grand-total {
		font-size: 1rem;
		font-weight: 700;
		text-align: right;
		color: var(--success);
	}

	/* Tables */
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th {
		text-align: left;
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--border);
		color: var(--text-muted);
		font-weight: 500;
	}

	td {
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--border);
	}

	tr:last-child td {
		border-bottom: none;
	}

	tr:hover td {
		background: var(--surface2);
	}

	.buy-list-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.buy-list-header h2 {
		margin: 0;
	}

	.not-found-list {
		margin: 0;
		padding-left: 1.25rem;
		color: var(--text-muted);
	}

	.not-found-list li {
		padding: 0.2rem 0;
	}

	.warn-icon {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		font-size: 0.9rem;
		color: var(--warning);
		cursor: default;
		line-height: 1;
	}

	/* Native tooltip via title attr — browser handles the rest */
	.has-warning {
		border-color: color-mix(in srgb, var(--warning) 40%, var(--border));
	}

	/* Debug panel */
	.debug-section {
		padding-bottom: 0.75rem;
	}

	.debug-toggle {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.85rem;
		padding: 0;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
		width: 100%;
		text-align: left;
	}

	.debug-toggle:hover {
		color: var(--text);
	}

	.debug-chevron {
		font-size: 0.7rem;
		transition: transform 0.15s;
		display: inline-block;
	}

	.debug-chevron.open {
		transform: rotate(90deg);
	}

	.debug-scroll {
		overflow-x: auto;
		margin-top: 0.75rem;
	}

	.debug-table {
		font-size: 0.8rem;
		white-space: nowrap;
	}

	.debug-table th {
		font-size: 0.75rem;
		padding: 0.4rem 0.6rem;
	}

	.debug-table td {
		padding: 0.35rem 0.6rem;
		font-variant-numeric: tabular-nums;
	}

	.debug-card-col {
		font-weight: 500;
		position: sticky;
		left: 0;
		background: var(--surface);
		z-index: 1;
	}

	tr:hover .debug-card-col {
		background: var(--surface2);
	}

	.debug-found {
		color: var(--text);
	}

	.debug-notfound {
		color: var(--text-muted);
	}

	.debug-qty {
		font-size: 0.7rem;
		color: var(--text-muted);
		margin-left: 0.2rem;
	}

	.debug-na {
		color: var(--border);
	}
</style>
