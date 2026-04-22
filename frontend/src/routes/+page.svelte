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
	// Printing picker
	// -------------------------------------------------------------------------
	let pickerCard: string | null = null;
	let pickerIdx = 0;

	// All in-stock printings per card, sorted cheapest first
	$: cardPrintings = (() => {
		const raw = $jobState?.raw_vendor_results;
		if (!raw) return {} as Record<string, import('$lib/types').CardPrice[]>;
		const result: Record<string, import('$lib/types').CardPrice[]> = {};
		for (const prices of Object.values(raw)) {
			for (const p of prices) {
				if (p.found && p.price != null && p.quantity_available > 0) {
					(result[p.original_query] ??= []).push(p);
				}
			}
		}
		for (const key of Object.keys(result)) {
			result[key].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
		}
		return result;
	})();

	// Group printings by unique set+CN+foil combination, sorted by cheapest vendor price
	$: pickerGroups = (() => {
		if (!pickerCard) return [] as import('$lib/types').CardPrice[][];
		const all = cardPrintings[pickerCard] ?? [];
		const map = new Map<string, import('$lib/types').CardPrice[]>();
		for (const p of all) {
			const key = `${p.set_code ?? ''}|${p.collector_number ?? ''}|${p.foil}`;
			const group = map.get(key);
			if (group) group.push(p);
			else map.set(key, [p]);
		}
		return [...map.values()].sort(
			(a, b) =>
				Math.min(...a.map((p) => p.price ?? Infinity)) -
				Math.min(...b.map((p) => p.price ?? Infinity))
		);
	})();

	$: pickerGroup = pickerGroups[pickerIdx] ?? null;
	$: pickerGroupCheapest = pickerGroups[0]
		? Math.min(...pickerGroups[0].map((p) => p.price ?? Infinity))
		: Infinity;

	function scryfallUrl(name: string, setCode: string | null, cn: string | null): string {
		if (setCode && cn && /^[A-Z0-9]{2,6}$/.test(setCode)) {
			return `https://api.scryfall.com/cards/${setCode.toLowerCase()}/${cn}?format=image&version=normal`;
		}
		return `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(name)}&format=image&version=normal`;
	}

	function openPicker(card: string) {
		pickerCard = card;
		pickerIdx = 0;
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
	function vendorFeatureIcons(v: import('$lib/types').VendorMeta): string {
		const parts: string[] = [];
		if (v.supports_set_info) parts.push('🃏');
		if (v.supports_foil) parts.push('✨');
		return parts.join(' ');
	}

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

	// -------------------------------------------------------------------------
	// Debug mock data
	// -------------------------------------------------------------------------
	function loadDebugData() {
		const mockRaw: Record<string, import('$lib/types').CardPrice[]> = {
			MagiCarte: [
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 2.30, website: 'MagiCarte', found: true, quantity_available: 4, set_code: 'CMM', collector_number: '396', foil: false },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 2.70, website: 'MagiCarte', found: true, quantity_available: 2, set_code: 'C11', collector_number: '196', foil: false },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 4.50, website: 'MagiCarte', found: true, quantity_available: 1, set_code: 'CMM', collector_number: '396', foil: true },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 1.80, website: 'MagiCarte', found: true, quantity_available: 3, set_code: 'C14', collector_number: '227', foil: false },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 0.50, website: 'MagiCarte', found: true, quantity_available: 8, set_code: 'CMM', collector_number: '349', foil: false },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 0.60, website: 'MagiCarte', found: true, quantity_available: 3, set_code: 'C21', collector_number: '281', foil: false },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 1.80, website: 'MagiCarte', found: true, quantity_available: 1, set_code: 'CLB', collector_number: '333', foil: true },
			],
			CryptMTG: [
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 2.20, website: 'CryptMTG', found: true, quantity_available: 6, set_code: 'CMM', collector_number: '396', foil: false },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 2.60, website: 'CryptMTG', found: true, quantity_available: 1, set_code: 'BLC', collector_number: '128', foil: false },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 3.90, website: 'CryptMTG', found: true, quantity_available: 2, set_code: 'BLC', collector_number: '128', foil: true },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 0.45, website: 'CryptMTG', found: true, quantity_available: 12, set_code: 'CMM', collector_number: '349', foil: false },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 1.20, website: 'CryptMTG', found: true, quantity_available: 2, set_code: 'CMM', collector_number: '349', foil: true },
			],
			'Mythic Store': [
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 3.10, website: 'Mythic Store', found: true, quantity_available: 3, set_code: 'C16', collector_number: '207', foil: false },
				{ card_name: 'Sol Ring', original_query: 'Sol Ring', price: 1.75, website: 'Mythic Store', found: true, quantity_available: 2, set_code: 'C14', collector_number: '227', foil: false },
				{ card_name: 'Command Tower', original_query: 'Command Tower', price: 0.55, website: 'Mythic Store', found: true, quantity_available: 5, set_code: 'C11', collector_number: '203', foil: false },
			],
		};

		jobState.set({
			job_id: 'debug',
			status: 'complete',
			vendor_progress: { MagiCarte: 'complete', CryptMTG: 'complete', 'Mythic Store': 'complete' },
			raw_vendor_results: mockRaw,
			parsed_cards: [
				{ quantity: 1, name: 'Sol Ring', set_code: null, collector_number: null },
				{ quantity: 1, name: 'Command Tower', set_code: null, collector_number: null },
			],
			error: null,
		});

		selectedVendors.set(new Set(['MagiCarte', 'CryptMTG', 'Mythic Store']));

		results.set({
			best_prices: {
				'Sol Ring': { quantity_needed: 1, best_price: 1.75, website: 'Mythic Store', quantity_available: 2 },
				'Command Tower': { quantity_needed: 1, best_price: 0.45, website: 'CryptMTG', quantity_available: 12 },
			},
			buy_lists: {
				'Mythic Store': [{ card: 'Sol Ring', quantity: 1, price_per_unit: 1.75, total_price: 1.75 }],
				CryptMTG: [{ card: 'Command Tower', quantity: 1, price_per_unit: 0.45, total_price: 0.45 }],
			},
			summary: {
				'Mythic Store': { total_cards: 1, total_price: 1.75, shipping_cost: 10.0, effective_total: 11.75 },
				CryptMTG: { total_cards: 1, total_price: 0.45, shipping_cost: 0, effective_total: 0.45 },
			},
			not_found: [],
			warnings: [],
		});

		phase.set('results');
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
						{#if vendorFeatureIcons(v)}
							<span class="feature-icons">{vendorFeatureIcons(v)}</span>
						{/if}
						<span class="ship-label">{v.fulfillment_label}</span>
					</label>
				{/each}
			</div>
			<p class="vendor-legend">🃏 set / collector #&nbsp;&nbsp;✨ foil detection</p>

			<div class="action-row">
				<button
					class="btn-primary"
					on:click={handleScrape}
					disabled={$phase === 'scraping' || !$cardList.trim() || $enabledVendors.size === 0}
				>
					{$phase === 'scraping' ? 'Searching…' : 'Find Best Prices'}
				</button>
				<button class="btn-debug" on:click={loadDebugData} disabled={$phase === 'scraping'}>
					⚙ Debug
				</button>
			</div>
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
							{#if vendorFeatureIcons(v)}
								<span class="feature-icons">{vendorFeatureIcons(v)}</span>
							{/if}
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
									<td>
										{card}
										{#if (cardPrintings[card]?.length ?? 0) > 0}
											<button class="btn-picker" on:click={() => openPicker(card)}>🔍</button>
										{/if}
									</td>
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
	<!-- Printing picker modal -->
	{#if pickerCard && pickerGroup}
		{@const rep = pickerGroup[0]}
		{@const groupMin = Math.min(...pickerGroup.map((p) => p.price ?? Infinity))}
		{@const diff = groupMin - pickerGroupCheapest}
		<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
		<div class="modal-backdrop" on:click|self={() => (pickerCard = null)}>
			<div class="modal">
				<div class="modal-header">
					<h2>{pickerCard}</h2>
					<span class="picker-counter">{pickerIdx + 1} / {pickerGroups.length}</span>
					<button class="btn-close" on:click={() => (pickerCard = null)}>✕</button>
				</div>
				<div class="modal-body">
					<button
						class="picker-nav"
						disabled={pickerIdx === 0}
						on:click={() => pickerIdx--}
					>‹</button>

					<div class="picker-card">
						<img
							src={scryfallUrl(pickerCard, rep.set_code, rep.collector_number)}
							alt={pickerCard}
						/>
						<div class="picker-meta">
							{#if rep.set_code}<span class="badge">{rep.set_code}</span>{/if}
							{#if rep.collector_number}<span class="badge muted">#{rep.collector_number}</span>{/if}
							{#if rep.foil}<span class="badge foil">✨ Foil</span>{/if}
							{#if diff === 0}
								<span class="badge best">★ Best</span>
							{:else}
								<span class="badge worse">+{fmt(diff)}</span>
							{/if}
						</div>
						<div class="picker-vendors">
							{#each pickerGroup as p, i}
								<div class="vendor-chip">
									<span class="vendor-num">{i + 1}</span>
									<span class="vendor-name">{p.website}</span>
									<span class="vendor-price">{fmt(p.price)}</span>
									<span class="vendor-qty">({p.quantity_available})</span>
								</div>
							{/each}
						</div>
					</div>

					<button
						class="picker-nav"
						disabled={pickerIdx >= pickerGroups.length - 1}
						on:click={() => pickerIdx++}
					>›</button>
				</div>
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

	.feature-icons {
		font-size: 0.8rem;
		opacity: 0.75;
	}

	.vendor-legend {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
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

	.action-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.btn-debug {
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text-muted);
		padding: 0.65rem 1rem;
		font-size: 0.85rem;
		cursor: pointer;
	}
	.btn-debug:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--text);
	}
	.btn-debug:disabled {
		opacity: 0.4;
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

	/* ---- Printing picker ---- */
	.btn-picker {
		background: none;
		border: none;
		cursor: pointer;
		padding: 0 0.25rem;
		font-size: 0.85rem;
		opacity: 0.6;
		vertical-align: middle;
	}
	.btn-picker:hover {
		opacity: 1;
	}

	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.65);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.modal {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 1.5rem;
		width: min(480px, 95vw);
		max-height: 90vh;
		overflow-y: auto;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
		gap: 0.5rem;
	}

	.modal-header h2 {
		margin: 0;
		flex: 1;
	}

	.picker-counter {
		color: var(--text-muted);
		font-size: 0.85rem;
		white-space: nowrap;
	}

	.btn-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
	}
	.btn-close:hover {
		color: var(--text);
	}

	.modal-body {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		justify-content: center;
	}

	/* ---- Picker carousel ---- */
	.picker-nav {
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		font-size: 2rem;
		line-height: 1;
		padding: 0.5rem 0.75rem;
		cursor: pointer;
		flex-shrink: 0;
	}
	.picker-nav:disabled {
		opacity: 0.2;
		cursor: default;
	}
	.picker-nav:not(:disabled):hover {
		background: var(--surface2);
	}

	.picker-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
	}

	.picker-card img {
		border-radius: 8px;
		width: 220px;
		display: block;
	}

	.picker-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		justify-content: center;
	}

	.badge {
		font-size: 0.75rem;
		padding: 0.2rem 0.5rem;
		border-radius: 999px;
		background: var(--surface2);
		border: 1px solid var(--border);
	}
	.badge.muted { color: var(--text-muted); }
	.badge.foil { background: rgba(255, 215, 0, 0.15); border-color: gold; }
	.badge.best { background: rgba(80, 200, 120, 0.2); border-color: #50c878; color: #50c878; font-weight: 600; }
	.badge.worse { color: var(--text-muted); }

	.picker-vendors {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		width: 100%;
	}

	.vendor-chip {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: var(--surface2);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.35rem 0.6rem;
		font-size: 0.85rem;
	}

	.vendor-num {
		background: var(--accent);
		color: #000;
		border-radius: 50%;
		width: 1.4em;
		height: 1.4em;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 700;
		flex-shrink: 0;
	}

	.vendor-name { flex: 1; }
	.vendor-price { font-weight: 600; }
	.vendor-qty { color: var(--text-muted); font-size: 0.8rem; }
</style>
