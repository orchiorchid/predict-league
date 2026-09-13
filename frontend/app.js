// Prediction League App Client with Responsive Modal & Mobile Tricks

let globalData = null;
let currentTab = 'overall';
let currentCategory = 'all'; // 'all', 'PL', 'UCL', 'CUP'
let currentDistRound = 'r6';
let selectedUser = null;
let currentUserProfileData = null;
let selectedModalRound = 'r6';
let modalCurrentCategory = 'all'; // 'all', 'PL', 'UCL', 'CUP'
let isModalRoundsExpanded = false;
let lastSyncTimestamp = null;

// DOM Elements
const syncStatusEl = document.getElementById('sync-status');
const syncDot = document.getElementById('sync-dot');
const syncSpinner = document.getElementById('sync-spinner');

const refreshBtn = document.getElementById('refresh-btn');
const refreshIcon = document.getElementById('refresh-icon');
const refreshSpinner = document.getElementById('refresh-spinner');
const refreshText = document.getElementById('refresh-text');

const searchInput = document.getElementById('search-input');
const searchClear = document.getElementById('search-clear');
const searchSpinner = document.getElementById('search-spinner');
const autocompleteList = document.getElementById('autocomplete-list');
const quickChips = document.getElementById('quick-chips');

// Navigation & Category Elements
const roundJumpSelect = document.getElementById('round-jump-select');
const tournamentCategoryFilters = document.getElementById('tournament-category-filters');
const modalCatFilters = document.getElementById('modal-cat-filters');
const toggleAllRoundsBtn = document.getElementById('toggle-all-rounds-btn');
const modalRoundsWrapper = document.getElementById('modal-rounds-wrapper');
const toggleRoundsText = document.getElementById('toggle-rounds-text');
const toggleRoundsIcon = document.getElementById('toggle-rounds-icon');

// Modal Elements
const userModal = document.getElementById('user-modal');
const modalBackdrop = document.getElementById('modal-backdrop');
const closeModalBtn = document.getElementById('close-modal-btn');
const copyLinkBtn = document.getElementById('copy-link-btn');
const modalLoadingOverlay = document.getElementById('modal-loading-overlay');

const profileUsername = document.getElementById('profile-username');
const profileRank = document.getElementById('profile-rank');
const profileTotalScore = document.getElementById('profile-total-score');
const profileMedal = document.getElementById('profile-medal');
const profileAvatar = document.getElementById('user-avatar');
const profileRoundsGrid = document.getElementById('profile-rounds-grid');
const profilePredictionsContainer = document.getElementById('profile-predictions-container');
const profilePredictionsTitle = document.getElementById('profile-predictions-title');
const profileR5SummaryBadge = document.getElementById('profile-r5-summary-badge');
const profileAliasesBadge = document.getElementById('profile-aliases-badge');
const modalRoundTabs = document.getElementById('modal-round-tabs');

const tabsContainer = document.getElementById('tabs-container');
const distTabsContainer = document.getElementById('dist-tabs-container');
const tableHeaders = document.getElementById('table-headers');
const tableBody = document.getElementById('table-body');
const tableFilterInput = document.getElementById('table-filter-input');
const tableCountLabel = document.getElementById('table-count-label');

const matchesGrid = document.getElementById('matches-grid');

// ==========================================
// Initialization
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await loadData(false);

  // Check URL params for pre-selected user
  const urlParams = new URLSearchParams(window.location.search);
  const userParam = urlParams.get('user');
  if (userParam) {
    selectUser(userParam);
  }

  // Auto update relative time every 10 seconds
  setInterval(updateRelativeSyncTime, 10000);
});

function setupEventListeners() {
  // Refresh button
  refreshBtn.addEventListener('click', async () => {
    setRefreshLoading(true);
    try {
      await loadData(true);
      showToast('Data refreshed from Google Sheets!', 'refresh-cw');
      if (selectedUser) {
        await selectUser(selectedUser);
      }
    } finally {
      setRefreshLoading(false);
    }
  });

  // Search input with debounce and search spinner
  let debounceTimeout = null;
  searchInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    if (val.length === 0) {
      searchClear.classList.add('hidden');
      searchSpinner.classList.add('hidden');
      autocompleteList.classList.add('hidden');
      clearTimeout(debounceTimeout);
      return;
    }

    // Show search spinner while typing/debouncing
    searchClear.classList.add('hidden');
    searchSpinner.classList.remove('hidden');

    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
      handleSearchInput(val);
      searchSpinner.classList.add('hidden');
      searchClear.classList.remove('hidden');
    }, 180);
  });

  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    searchClear.classList.add('hidden');
    searchSpinner.classList.add('hidden');
    autocompleteList.classList.add('hidden');
    searchInput.focus();
  });

  // Close autocomplete on click outside
  document.addEventListener('click', (e) => {
    if (!document.getElementById('search-container').contains(e.target)) {
      autocompleteList.classList.add('hidden');
    }
  });

  // Modal close handlers
  closeModalBtn.addEventListener('click', closeModal);
  modalBackdrop.addEventListener('click', closeModal);

  // ESC key to close modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !userModal.classList.contains('hidden')) {
      closeModal();
    }
  });

  // Back button handling on mobile
  window.addEventListener('popstate', (e) => {
    const urlParams = new URLSearchParams(window.location.search);
    const userParam = urlParams.get('user');
    if (!userParam && !userModal.classList.contains('hidden')) {
      closeModal(false);
    } else if (userParam) {
      selectUser(userParam, false);
    }
  });

  // Copy Profile Link Button
  copyLinkBtn.addEventListener('click', () => {
    if (!selectedUser) return;
    const url = new URL(window.location.href);
    url.searchParams.set('user', selectedUser);
    navigator.clipboard.writeText(url.href).then(() => {
      showToast('Profile link copied to clipboard!', 'check');
    }).catch(() => {
      showToast('Failed to copy link', 'x');
    });
  });

  // Table tabs
  tabsContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('.tab-btn');
    if (!btn) return;
    const tab = btn.getAttribute('data-tab');
    if (tab && tab !== currentTab) {
      currentTab = tab;
      updateActiveTabUI();
      renderLeaderboardTable();
    }
  });

  // Tournament Category Filters (All, PL, UCL, Cups)
  if (tournamentCategoryFilters) {
    tournamentCategoryFilters.addEventListener('click', (e) => {
      const btn = e.target.closest('.cat-filter-btn');
      if (!btn) return;
      const cat = btn.getAttribute('data-cat');
      if (cat && cat !== currentCategory) {
        currentCategory = cat;
        updateCategoryFilterUI();
        renderTabsNavigation();
        renderLeaderboardTable();
      }
    });
  }

  // Quick Jump Select dropdown for 50+ rounds
  if (roundJumpSelect) {
    roundJumpSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val) {
        currentTab = val;
        updateActiveTabUI();
        renderLeaderboardTable();
      }
    });
  }

  // Table filter
  tableFilterInput.addEventListener('input', () => {
    renderLeaderboardTable();
  });

  // Distribution round tabs
  if (distTabsContainer) {
    distTabsContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.dist-tab-btn');
      if (!btn) return;
      const round = btn.getAttribute('data-dist-tab');
      if (round && round !== currentDistRound) {
        currentDistRound = round;
        updateDistTabsUI();
        renderMatchDistributions();
      }
    });
  }

  // Modal Category Filters (All, PL, UCL, Cups)
  if (modalCatFilters) {
    modalCatFilters.addEventListener('click', (e) => {
      const btn = e.target.closest('.mcat-btn');
      if (!btn) return;
      const cat = btn.getAttribute('data-mcat');
      if (cat && cat !== modalCurrentCategory) {
        modalCurrentCategory = cat;
        updateModalCategoryFilterUI();
        if (currentUserProfileData) {
          // If the currently selected round does not belong to the selected category,
          // switch to the best matching round in this category (active round or latest)
          const matchingRounds = (currentUserProfileData.round_scores || []).filter(rs => {
            if (cat === 'all') return true;
            return getRoundCategory(rs.round_name) === cat;
          });
          if (matchingRounds.length > 0) {
            const currentStillMatches = matchingRounds.some(rs => rs.round_id === selectedModalRound);
            if (!currentStillMatches) {
              const activeInCat = matchingRounds.find(rs => rs.status === 'active' || rs.round_id === 'r6');
              selectedModalRound = activeInCat ? activeInCat.round_id : matchingRounds[matchingRounds.length - 1].round_id;
            }
          }
          renderUserProfileRoundCards(currentUserProfileData);
          renderRoundPredictions(selectedModalRound);
        }
      }
    });
  }

  // Modal Accordion toggle button (Expand all cards / Collapse)
  if (toggleAllRoundsBtn && modalRoundsWrapper) {
    toggleAllRoundsBtn.addEventListener('click', () => {
      isModalRoundsExpanded = !isModalRoundsExpanded;
      if (isModalRoundsExpanded) {
        modalRoundsWrapper.classList.remove('max-h-[175px]', 'sm:max-h-[220px]');
        modalRoundsWrapper.classList.add('max-h-[600px]');
        if (toggleRoundsText) toggleRoundsText.textContent = 'Collapse';
        if (toggleRoundsIcon) toggleRoundsIcon.classList.add('rotate-180');
      } else {
        modalRoundsWrapper.classList.remove('max-h-[600px]');
        modalRoundsWrapper.classList.add('max-h-[175px]', 'sm:max-h-[220px]');
        if (toggleRoundsText) toggleRoundsText.textContent = 'Expand All';
        if (toggleRoundsIcon) toggleRoundsIcon.classList.remove('rotate-180');
      }
      if (window.lucide) lucide.createIcons();
    });
  }
}

function setRefreshLoading(isLoading) {
  if (isLoading) {
    refreshBtn.disabled = true;
    refreshIcon.classList.add('hidden');
    refreshSpinner.classList.remove('hidden');
    refreshText.textContent = 'Refreshing...';
    syncDot.classList.add('hidden');
    syncSpinner.classList.remove('hidden');
    syncStatusEl.textContent = 'Syncing with Google Sheets...';
  } else {
    refreshBtn.disabled = false;
    refreshSpinner.classList.add('hidden');
    refreshIcon.classList.remove('hidden');
    refreshText.textContent = 'Refresh';
    syncSpinner.classList.add('hidden');
    syncDot.classList.remove('hidden');
  }
}

// Toast notification helper
function showToast(message, icon = 'check') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<i data-lucide="${icon}" class="w-4 h-4 text-indigo-400"></i> <span>${message}</span>`;
  container.appendChild(toast);
  if (window.lucide) lucide.createIcons();

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 2400);
}

// ==========================================
// Data Fetching
// ==========================================
async function loadData(force = false) {
  try {
    if (!force) {
      syncDot.classList.add('hidden');
      syncSpinner.classList.remove('hidden');
      syncStatusEl.textContent = 'Fetching data...';
    }

    const url = `/api/data${force ? '?fresh=true' : ''}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);

    globalData = await res.json();
    lastSyncTimestamp = new Date();

    syncSpinner.classList.add('hidden');
    syncDot.classList.remove('hidden');
    updateRelativeSyncTime();

    renderTabsNavigation();
    renderQuickChips();
    renderLeaderboardTable();
    renderMatchDistributions();

    if (window.lucide) {
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Failed to load data:', err);
    syncSpinner.classList.add('hidden');
    syncDot.classList.remove('hidden');
    syncStatusEl.textContent = 'Sync failed';
  }
}

function updateRelativeSyncTime() {
  if (!lastSyncTimestamp) return;
  const now = new Date();
  const diffSec = Math.round((now - lastSyncTimestamp) / 1000);
  let text = 'just now';
  if (diffSec >= 60) {
    const mins = Math.floor(diffSec / 60);
    text = `${mins}m ago`;
  } else if (diffSec > 5) {
    text = `${diffSec}s ago`;
  }
  syncStatusEl.textContent = `Updated: ${text}`;
}

// ==========================================
// Tournament Round & Category Helpers
// ==========================================
function getRoundCategory(roundName) {
  if (!roundName) return 'PL';
  const n = roundName.toUpperCase();
  if (n.includes('UCL') || n.includes('CHAMPIONS') || n.includes('CL ')) return 'UCL';
  if (n.includes('LC') || n.includes('CUP') || n.includes('FA') || n.includes('1/16') || n.includes('1/8') || n.includes('1/4') || n.includes('SEMI') || n.includes('FINAL')) return 'CUP';
  return 'PL';
}

function getShortRoundLabel(roundName) {
  if (!roundName) return '';
  const mPl = roundName.match(/PL\s*MD(\d+)/i);
  if (mPl) return `PL ${mPl[1]}`;
  const mUcl = roundName.match(/UCL\s*MD(\d+)/i);
  if (mUcl) return `CL ${mUcl[1]}`;
  const mLc = roundName.match(/LC\s*R?(\d+)/i);
  if (mLc) return `LC ${mLc[1]}`;
  const mFa = roundName.match(/FA\s*R?(\d+)/i);
  if (mFa) return `FA ${mFa[1]}`;
  const mR = roundName.match(/Round\s*(\d+)/i);
  if (mR) return `R${mR[1]}`;
  return roundName.length > 7 ? roundName.slice(0, 6) : roundName;
}

function updateCategoryFilterUI() {
  if (!tournamentCategoryFilters) return;
  tournamentCategoryFilters.querySelectorAll('.cat-filter-btn').forEach(btn => {
    const cat = btn.getAttribute('data-cat');
    if (cat === currentCategory) {
      btn.className = 'cat-filter-btn px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm shrink-0 active:scale-95 transition';
    } else {
      btn.className = 'cat-filter-btn px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800/90 text-slate-400 hover:text-white border border-slate-700/60 shrink-0 active:scale-95 transition';
    }
  });
}

function updateModalCategoryFilterUI() {
  if (!modalCatFilters) return;
  modalCatFilters.querySelectorAll('.mcat-btn').forEach(btn => {
    const cat = btn.getAttribute('data-mcat');
    if (cat === modalCurrentCategory) {
      btn.className = 'mcat-btn px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-600 text-white shrink-0 active:scale-95 transition';
    } else {
      btn.className = 'mcat-btn px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 hover:text-white shrink-0 active:scale-95 transition';
    }
  });
}

function renderTabsNavigation() {
  if (!globalData || !tabsContainer) return;

  const rounds = (globalData.rounds || []).filter(r => {
    if (currentCategory === 'all') return true;
    return getRoundCategory(r.name) === currentCategory;
  });

  // Render buttons in tabsContainer
  let html = `
    <button data-tab="overall" class="tab-btn px-3.5 py-2 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 whitespace-nowrap ${currentTab === 'overall' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white border border-slate-700/50'} shrink-0">
      <i data-lucide="globe" class="w-3.5 h-3.5"></i>
      <span>Overall Standings</span>
    </button>
  `;

  rounds.forEach(rd => {
    const isActive = rd.id === currentTab;
    const isRoundLive = rd.status === 'active';
    const shortLabel = getShortRoundLabel(rd.name);
    const liveDot = isRoundLive ? '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>' : '';
    html += `
      <button data-tab="${rd.id}" title="${rd.name}" class="tab-btn px-3.5 py-2 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 whitespace-nowrap ${isActive ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white border border-slate-700/50'} shrink-0">
        ${liveDot}
        <span>${shortLabel || rd.name}</span>
      </button>
    `;
  });

  tabsContainer.innerHTML = html;

  // Populate roundJumpSelect
  if (roundJumpSelect) {
    let selectHtml = `<option value="overall" ${currentTab === 'overall' ? 'selected' : ''}>🏆 Overall Standings</option>`;
    
    const allRounds = globalData.rounds || [];
    const plRounds = allRounds.filter(r => getRoundCategory(r.name) === 'PL');
    const uclRounds = allRounds.filter(r => getRoundCategory(r.name) === 'UCL');
    const cupRounds = allRounds.filter(r => getRoundCategory(r.name) === 'CUP');

    if (plRounds.length > 0) {
      selectHtml += `<optgroup label="⚽ Premier League">`;
      plRounds.forEach(r => {
        selectHtml += `<option value="${r.id}" ${currentTab === r.id ? 'selected' : ''}>${r.status === 'active' ? '🟢 ' : ''}${r.name}</option>`;
      });
      selectHtml += `</optgroup>`;
    }
    if (uclRounds.length > 0) {
      selectHtml += `<optgroup label="🌟 Champions League">`;
      uclRounds.forEach(r => {
        selectHtml += `<option value="${r.id}" ${currentTab === r.id ? 'selected' : ''}>${r.status === 'active' ? '🟢 ' : ''}${r.name}</option>`;
      });
      selectHtml += `</optgroup>`;
    }
    if (cupRounds.length > 0) {
      selectHtml += `<optgroup label="🏆 Cups">`;
      cupRounds.forEach(r => {
        selectHtml += `<option value="${r.id}" ${currentTab === r.id ? 'selected' : ''}>${r.status === 'active' ? '🟢 ' : ''}${r.name}</option>`;
      });
      selectHtml += `</optgroup>`;
    }

    roundJumpSelect.innerHTML = selectHtml;
  }

  if (window.lucide) lucide.createIcons();
}

// ==========================================
// Search & Autocomplete
// ==========================================
function handleSearchInput(query) {
  if (!query || !globalData) {
    autocompleteList.classList.add('hidden');
    return;
  }

  const q = query.toLowerCase();
  const matches = globalData.leaderboard.filter(u => {
    const matchName = u.username.toLowerCase().includes(q);
    const matchAlias = (u.aliases || []).some(a => a.toLowerCase().includes(q));
    return matchName || matchAlias;
  }).slice(0, 8);

  if (matches.length === 0) {
    autocompleteList.innerHTML = `
      <div class="px-4 py-3 text-xs text-slate-500 text-center">
        No participant found matching "${query}"
      </div>
    `;
    autocompleteList.classList.remove('hidden');
    return;
  }

  autocompleteList.innerHTML = matches.map(u => {
    const idx = u.username.toLowerCase().indexOf(q);
    let highlighted = u.username;
    if (idx !== -1) {
      const before = u.username.slice(0, idx);
      const match = u.username.slice(idx, idx + q.length);
      const after = u.username.slice(idx + q.length);
      highlighted = `${before}<span class="text-indigo-400 font-bold underline">${match}</span>${after}`;
    }

    let medal = '';
    if (u.rank === 1) medal = '🥇 ';
    else if (u.rank === 2) medal = '🥈 ';
    else if (u.rank === 3) medal = '🥉 ';

    const aliasInfo = u.aliases && u.aliases.length > 1 ? `<span class="text-[10px] text-slate-500 ml-1">(${u.aliases.join(', ')})</span>` : '';

    return `
      <div class="px-4 py-2.5 hover:bg-slate-800/80 cursor-pointer flex items-center justify-between transition active:bg-slate-700"
           onclick="selectUser('${u.username}')">
        <div class="flex items-center space-x-2">
          <span class="text-xs text-slate-400 w-8 font-mono">#${u.rank}</span>
          <span class="text-sm text-white font-medium">${medal}${highlighted}${aliasInfo}</span>
        </div>
        <span class="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 font-mono">
          ${u.total_score} pts
        </span>
      </div>
    `;
  }).join('');

  autocompleteList.classList.remove('hidden');
}

function renderQuickChips() {
  if (!globalData || !globalData.leaderboard) return;
  const topPlayers = globalData.leaderboard.slice(0, 5);
  quickChips.innerHTML = topPlayers.map(p => {
    let medal = '⭐';
    if (p.rank === 1) medal = '🥇';
    else if (p.rank === 2) medal = '🥈';
    else if (p.rank === 3) medal = '🥉';
    return `
      <button onclick="selectUser('${p.username}')" 
              class="px-2.5 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 hover:text-white border border-slate-700/60 text-slate-300 transition flex items-center gap-1.5 shadow-sm active:scale-95 shrink-0 text-xs">
        <span>${medal}</span>
        <span class="font-medium">${p.username}</span>
        <span class="text-slate-400 font-bold font-mono">(${p.total_score})</span>
      </button>
    `;
  }).join('');
}

// ==========================================
// Modal & User Profile Management
// ==========================================
async function selectUser(username, updateHistory = true) {
  autocompleteList.classList.add('hidden');
  searchInput.value = username;
  searchClear.classList.remove('hidden');

  // Open modal dialog / bottom sheet
  userModal.classList.remove('hidden');
  modalLoadingOverlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden'; // Lock background scrolling

  if (updateHistory) {
    const url = new URL(window.location);
    url.searchParams.set('user', username);
    window.history.pushState({ user: username }, '', url);
  }

  try {
    const res = await fetch(`/api/user/${encodeURIComponent(username)}`);
    if (!res.ok) throw new Error('User not found');
    const user = await res.json();

    selectedUser = user.username;
    renderUserProfile(user);

    if (window.lucide) lucide.createIcons();
  } catch (err) {
    console.error('Error selecting user:', err);
    showToast('Failed to load user profile', 'x');
  } finally {
    modalLoadingOverlay.classList.add('hidden');
  }
}

function closeModal(updateHistory = true) {
  userModal.classList.add('hidden');
  document.body.style.overflow = ''; // Restore scrolling
  selectedUser = null;

  if (updateHistory) {
    const url = new URL(window.location);
    url.searchParams.delete('user');
    window.history.pushState({}, '', url);
  }
}

function renderUserProfile(user) {
  currentUserProfileData = user;
  profileUsername.textContent = user.username;
  profileAvatar.textContent = user.username.slice(0, 2).toUpperCase();
  profileRank.textContent = `#${user.rank}`;
  profileTotalScore.textContent = `${user.total_score} pts`;

  // Aliases badge if username was merged
  if (user.aliases && user.aliases.length > 1) {
    profileAliasesBadge.textContent = `Aliases: ${user.aliases.join(', ')}`;
    profileAliasesBadge.classList.remove('hidden');
  } else {
    profileAliasesBadge.classList.add('hidden');
  }

  // Medal
  if (user.rank === 1) {
    profileMedal.textContent = '🥇 Champion';
    profileMedal.className = 'text-amber-400 text-xs sm:text-sm font-bold flex items-center gap-1 whitespace-nowrap';
    profileMedal.classList.remove('hidden');
  } else if (user.rank === 2) {
    profileMedal.textContent = '🥈 Runner-up';
    profileMedal.className = 'text-slate-300 text-xs sm:text-sm font-bold flex items-center gap-1 whitespace-nowrap';
    profileMedal.classList.remove('hidden');
  } else if (user.rank === 3) {
    profileMedal.textContent = '🥉 3rd Place';
    profileMedal.className = 'text-amber-600 text-xs sm:text-sm font-bold flex items-center gap-1 whitespace-nowrap';
    profileMedal.classList.remove('hidden');
  } else {
    profileMedal.classList.add('hidden');
  }

  // Choose default round to display in predictions:
  if (user.round_predictions && user.round_predictions['r6'] && user.round_predictions['r6'].length > 0) {
    selectedModalRound = 'r6';
  } else if (user.round_predictions && user.round_predictions['r5'] && user.round_predictions['r5'].length > 0) {
    selectedModalRound = 'r5';
  } else {
    selectedModalRound = (globalData && globalData.active_round_id) || 'r6';
  }

  updateModalCategoryFilterUI();
  renderUserProfileRoundCards(user);
  renderRoundPredictions(selectedModalRound);
}

function renderUserProfileRoundCards(user) {
  if (!profileRoundsGrid || !user || !user.round_scores) return;

  const filteredRounds = user.round_scores.filter(rs => {
    if (modalCurrentCategory === 'all') return true;
    return getRoundCategory(rs.round_name) === modalCurrentCategory;
  });

  if (filteredRounds.length === 0) {
    profileRoundsGrid.innerHTML = `
      <div class="col-span-full p-4 text-center text-xs text-slate-500 bg-slate-950/40 rounded-xl border border-slate-800">
        No rounds found in category "${modalCurrentCategory}".
      </div>
    `;
    return;
  }

  profileRoundsGrid.innerHTML = filteredRounds.map(rs => {
    const isSelected = rs.round_id === selectedModalRound;
    const isCurrent = rs.round_id === 'r6' || rs.status === 'active';
    const hasPreds = user.round_predictions && user.round_predictions[rs.round_id] && user.round_predictions[rs.round_id].length > 0;
    const scoreDisplay = rs.score !== null ? `${rs.score} pts` : '<span class="text-slate-500">—</span>';
    
    let statusText = 'Skipped';
    let statusClass = 'text-slate-500 bg-slate-800/40';
    if (isCurrent) {
      statusText = hasPreds ? 'Picks Submitted' : 'Pending Picks';
      statusClass = hasPreds ? 'text-emerald-400 bg-emerald-500/10 border border-emerald-500/20' : 'text-amber-400 bg-amber-500/10';
    } else if (hasPreds) {
      const correct = user.round_predictions[rs.round_id].filter(p => p.correct).length;
      statusText = `${correct}/${user.round_predictions[rs.round_id].length} correct`;
      statusClass = 'text-emerald-400 bg-emerald-500/10';
    } else if (rs.participated || rs.score !== null) {
      statusText = 'Score Logged';
      statusClass = 'text-indigo-400 bg-indigo-500/10';
    }

    const activeClasses = isSelected
      ? 'round-card-active border-indigo-500 bg-indigo-950/60 shadow-lg shadow-indigo-500/20 ring-2 ring-indigo-500/70'
      : (isCurrent ? 'bg-indigo-950/30 border-indigo-500/40 hover:border-indigo-400' : 'bg-slate-950/60 border-slate-800 hover:border-slate-700');

    return `
      <div onclick="switchModalRound('${rs.round_id}')" 
           class="p-3 rounded-xl border ${activeClasses} space-y-1 transition cursor-pointer active:scale-[0.97] select-none"
           title="Click to view ${rs.round_name} predictions">
        <div class="flex items-center justify-between gap-1">
          <span class="text-[10px] sm:text-[11px] font-semibold ${isSelected ? 'text-indigo-200' : 'text-slate-400'} truncate">${rs.round_name}</span>
          ${isCurrent ? '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" title="Active Round"></span>' : ''}
        </div>
        <div class="text-lg sm:text-xl font-black font-mono ${rs.score !== null ? 'text-white' : 'text-slate-600'}">
          ${scoreDisplay}
        </div>
        <div class="text-[9px] sm:text-[10px] font-medium px-1.5 py-0.2 rounded inline-block ${statusClass}">
          ${statusText}
        </div>
      </div>
    `;
  }).join('');
}

function switchModalRound(roundId) {
  if (!currentUserProfileData) return;
  selectedModalRound = roundId;
  renderUserProfileRoundCards(currentUserProfileData);
  renderRoundPredictions(selectedModalRound);
}
window.switchModalRound = switchModalRound;

function renderRoundPredictions(roundId) {
  if (!currentUserProfileData) return;
  const user = currentUserProfileData;
  const preds = (user.round_predictions && user.round_predictions[roundId]) || [];
  
  let roundDisplayName = roundId;
  let roundStatus = 'completed';
  if (globalData && globalData.rounds) {
    const rm = globalData.rounds.find(r => r.id === roundId);
    if (rm) {
      roundDisplayName = rm.name;
      roundStatus = rm.status;
    }
  }

  if (profilePredictionsTitle) {
    profilePredictionsTitle.textContent = `${roundDisplayName} Predictions`;
  }

  if (preds.length === 0) {
    profileR5SummaryBadge.textContent = 'No picks submitted';
    profileR5SummaryBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-medium whitespace-nowrap';

    profilePredictionsContainer.innerHTML = `
      <div class="p-8 text-center space-y-2">
        <i data-lucide="help-circle" class="w-8 h-8 text-slate-600 mx-auto mb-1"></i>
        <p class="text-xs sm:text-sm font-medium text-slate-300">No predictions submitted for ${roundDisplayName}.</p>
        <p class="text-[11px] text-slate-500">${user.username} did not submit picks for this round.</p>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  const isPending = preds.every(p => p.correct === null);
  if (isPending) {
    profileR5SummaryBadge.textContent = `${preds.length} picks submitted (Awaiting Results)`;
    profileR5SummaryBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 font-medium whitespace-nowrap';
  } else {
    const correctCount = preds.filter(p => p.correct).length;
    profileR5SummaryBadge.textContent = `${correctCount} / ${preds.length} correct (+${correctCount} pts)`;
    profileR5SummaryBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium whitespace-nowrap';
  }

  const outcomeShort = {
    'Home': '1 (Home)',
    'Away': '2 (Away)',
    'Draw': 'X (Draw)'
  };

  profilePredictionsContainer.innerHTML = `
    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-900/90 text-[10px] sm:text-[11px] text-slate-400 uppercase tracking-wider border-b border-slate-800 font-semibold sticky top-0">
          <tr>
            <th class="py-2.5 px-3 sm:px-4 w-8 font-mono">#</th>
            <th class="py-2.5 px-3 sm:px-4">Match</th>
            <th class="py-2.5 px-3 sm:px-4">Pick</th>
            <th class="py-2.5 px-3 sm:px-4 hidden sm:table-cell">Result</th>
            <th class="py-2.5 px-3 sm:px-4 text-right">Points</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60">
          ${preds.map((p, idx) => {
            let badge = '';
            if (p.correct === true) {
              badge = `<span class="inline-flex items-center gap-0.5 text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 text-[11px]">
                         <i data-lucide="check" class="w-3 h-3"></i> +1
                       </span>`;
            } else if (p.correct === false) {
              badge = `<span class="inline-flex items-center gap-0.5 text-rose-400 font-medium bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20 text-[11px]">
                         <i data-lucide="x" class="w-3 h-3"></i> 0
                       </span>`;
            } else {
              badge = `<span class="inline-flex items-center text-slate-400 bg-slate-800 px-2 py-0.5 rounded text-[11px]">
                         Pending
                       </span>`;
            }

            return `
              <tr class="hover:bg-slate-800/40 transition">
                <td class="py-2.5 px-3 sm:px-4 text-slate-500 font-mono text-[11px]">${idx + 1}</td>
                <td class="py-2.5 px-3 sm:px-4 text-white font-medium text-xs">
                  <div>${p.match}</div>
                  <div class="text-[10px] text-slate-400 sm:hidden mt-0.5">Result: ${outcomeShort[p.actual] || p.actual || '<span class="text-slate-500 italic">Pending</span>'}</div>
                </td>
                <td class="py-2.5 px-3 sm:px-4 font-semibold text-indigo-300 text-xs whitespace-nowrap">
                  ${outcomeShort[p.prediction] || p.prediction}
                </td>
                <td class="py-2.5 px-3 sm:px-4 text-slate-400 text-xs hidden sm:table-cell whitespace-nowrap">
                  ${outcomeShort[p.actual] || p.actual || '<span class="text-slate-500 italic">Pending</span>'}
                </td>
                <td class="py-2.5 px-3 sm:px-4 text-right">${badge}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

  const isPending = preds.every(p => p.correct === null);
  if (isPending) {
    profileR5SummaryBadge.textContent = `${preds.length} picks submitted (Awaiting Results)`;
    profileR5SummaryBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 font-medium whitespace-nowrap';
  } else {
    const correctCount = preds.filter(p => p.correct).length;
    profileR5SummaryBadge.textContent = `${correctCount} / ${preds.length} correct (+${correctCount} pts)`;
    profileR5SummaryBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium whitespace-nowrap';
  }

  const outcomeShort = {
    'Home': '1 (Home)',
    'Away': '2 (Away)',
    'Draw': 'X (Draw)'
  };

  profilePredictionsContainer.innerHTML = `
    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-900/90 text-[10px] sm:text-[11px] text-slate-400 uppercase tracking-wider border-b border-slate-800 font-semibold sticky top-0">
          <tr>
            <th class="py-2.5 px-3 sm:px-4 w-8 font-mono">#</th>
            <th class="py-2.5 px-3 sm:px-4">Match</th>
            <th class="py-2.5 px-3 sm:px-4">Pick</th>
            <th class="py-2.5 px-3 sm:px-4 hidden sm:table-cell">Result</th>
            <th class="py-2.5 px-3 sm:px-4 text-right">Points</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60">
          ${preds.map((p, idx) => {
            let badge = '';
            if (p.correct === true) {
              badge = `<span class="inline-flex items-center gap-0.5 text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 text-[11px]">
                         <i data-lucide="check" class="w-3 h-3"></i> +1
                       </span>`;
            } else if (p.correct === false) {
              badge = `<span class="inline-flex items-center gap-0.5 text-rose-400 font-medium bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20 text-[11px]">
                         <i data-lucide="x" class="w-3 h-3"></i> 0
                       </span>`;
            } else {
              badge = `<span class="inline-flex items-center text-slate-400 bg-slate-800 px-2 py-0.5 rounded text-[11px]">
                         Pending
                       </span>`;
            }

            return `
              <tr class="hover:bg-slate-800/40 transition">
                <td class="py-2.5 px-3 sm:px-4 text-slate-500 font-mono text-[11px]">${idx + 1}</td>
                <td class="py-2.5 px-3 sm:px-4 text-white font-medium text-xs">
                  <div>${p.match}</div>
                  <div class="text-[10px] text-slate-400 sm:hidden mt-0.5">Result: ${outcomeShort[p.actual] || p.actual || '<span class="text-slate-500 italic">Pending</span>'}</div>
                </td>
                <td class="py-2.5 px-3 sm:px-4 font-semibold text-indigo-300 text-xs whitespace-nowrap">
                  ${outcomeShort[p.prediction] || p.prediction}
                </td>
                <td class="py-2.5 px-3 sm:px-4 text-slate-400 text-xs hidden sm:table-cell whitespace-nowrap">
                  ${outcomeShort[p.actual] || p.actual || '<span class="text-slate-500 italic">Pending</span>'}
                </td>
                <td class="py-2.5 px-3 sm:px-4 text-right">${badge}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

window.goToRoundTable = function(roundId) {
  closeModal();
  currentTab = roundId;
  updateActiveTabUI();
  renderLeaderboardTable();
  const tableSec = document.getElementById('leaderboard-table');
  if (tableSec) {
    tableSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

// ==========================================
// Leaderboard Tabs & Rendering
// ==========================================
function updateActiveTabUI() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const tab = btn.getAttribute('data-tab');
    if (tab === currentTab) {
      btn.className = 'tab-btn px-3.5 py-2 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 whitespace-nowrap bg-indigo-600 text-white shadow-md shadow-indigo-600/30 shrink-0';
    } else {
      btn.className = 'tab-btn px-3.5 py-2 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 whitespace-nowrap bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white border border-slate-700/50 shrink-0';
    }
  });

  if (roundJumpSelect) {
    roundJumpSelect.value = currentTab;
  }
}

function renderLeaderboardTable() {
  if (!globalData) return;

  const filter = (tableFilterInput.value || '').trim().toLowerCase();

  if (currentTab === 'overall') {
    renderOverallTable(filter);
  } else {
    renderRoundTable(currentTab, filter);
  }

  if (window.lucide) lucide.createIcons();
}

function renderOverallTable(filter) {
  const allRounds = (globalData && globalData.rounds) || [];
  const displayedRounds = allRounds.filter(r => {
    if (currentCategory === 'all') return true;
    return getRoundCategory(r.name) === currentCategory;
  });

  const roundColsHtml = displayedRounds.map(r => {
    const shortLabel = getShortRoundLabel(r.name);
    return `<th class="py-3 px-2 text-center hidden md:table-cell text-[11px] font-mono whitespace-nowrap" title="${r.name}">${shortLabel}</th>`;
  }).join('');

  tableHeaders.innerHTML = `
    <tr>
      <th class="py-3 px-2 sm:px-3 sticky-col-1 font-mono whitespace-nowrap">Rank</th>
      <th class="py-3 px-3 sm:px-4 sticky-col-2 whitespace-nowrap">Participant</th>
      ${roundColsHtml}
      <th class="py-3 px-3 sm:px-4 text-right whitespace-nowrap">Total Points</th>
    </tr>
  `;

  let users = globalData.leaderboard || [];
  if (filter) {
    users = users.filter(u => {
      const matchName = u.username.toLowerCase().includes(filter);
      const matchAlias = (u.aliases || []).some(a => a.toLowerCase().includes(filter));
      return matchName || matchAlias;
    });
  }

  tableCountLabel.textContent = `Showing ${users.length} of ${globalData.total_participants} participants`;

  const totalCols = 3 + displayedRounds.length;

  if (users.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="${totalCols}" class="text-center py-8 text-slate-500 text-xs">
          No participants match "${filter}"
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = users.map(u => {
    let rankBadge = `<span class="font-mono text-slate-400 font-semibold whitespace-nowrap">#${u.rank}</span>`;
    let rowClass = 'hover:bg-slate-800/60 cursor-pointer transition active:bg-slate-800/80';
    if (u.rank === 1) {
      rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-amber-400 whitespace-nowrap">🥇 1</span>`;
    } else if (u.rank === 2) {
      rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-slate-300 whitespace-nowrap">🥈 2</span>`;
    } else if (u.rank === 3) {
      rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-amber-600 whitespace-nowrap">🥉 3</span>`;
    }

    const isSelected = selectedUser && selectedUser.toLowerCase() === u.username.toLowerCase();
    if (isSelected) {
      rowClass += ' selected-row bg-indigo-900/30 border-l-2 border-indigo-500';
    }

    const rCellsHtml = displayedRounds.map(r => {
      const val = u.round_scores ? u.round_scores[r.id] : null;
      if (r.id === 'r6' || r.status === 'active') {
        if (u.has_active_predictions) {
          return '<td class="py-3 px-2 text-center hidden md:table-cell text-xs"><span class="text-emerald-400 font-semibold text-[11px]" title="Predictions submitted (Pending results)">0*</span></td>';
        }
        return '<td class="py-3 px-2 text-center hidden md:table-cell text-xs"><span class="text-slate-600">—</span></td>';
      }
      const scoreDisplay = (val !== null && val !== undefined) ? `<span class="text-slate-300 font-mono">${val}</span>` : '<span class="text-slate-600">—</span>';
      return `<td class="py-3 px-2 text-center hidden md:table-cell text-xs">${scoreDisplay}</td>`;
    }).join('');

    const aliasesNotice = u.aliases && u.aliases.length > 1 ? `<span class="text-[10px] text-slate-500 hidden sm:inline">(${u.aliases.join(', ')})</span>` : '';
    const activeBadge = u.has_active_predictions ? '<span class="text-[10px] font-bold px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 shrink-0" title="Active round predictions submitted">Active ✓</span>' : '';

    return `
      <tr class="${rowClass}" onclick="selectUser('${u.username}')">
        <td class="py-3 px-2 sm:px-3 sticky-col-1 whitespace-nowrap">${rankBadge}</td>
        <td class="py-3 px-3 sm:px-4 sticky-col-2 whitespace-nowrap">
          <div class="flex items-center space-x-1.5">
            <span class="font-semibold text-white text-xs sm:text-sm hover:underline">${u.username}</span>
            ${aliasesNotice}
            ${activeBadge}
          </div>
        </td>
        ${rCellsHtml}
        <td class="py-3 px-3 sm:px-4 text-right whitespace-nowrap">
          <span class="text-xs sm:text-sm font-black text-emerald-400 font-mono">${u.total_score}</span>
        </td>
      </tr>
    `;
  }).join('');
}

function renderRoundTable(roundId, filter) {
  const roundMeta = (globalData.rounds && globalData.rounds.find(r => r.id === roundId)) || { name: roundId, status: 'completed' };
  const isRoundActive = roundMeta.status === 'active';

  tableHeaders.innerHTML = `
    <tr>
      <th class="py-3 px-2 sm:px-3 sticky-col-1 font-mono whitespace-nowrap">Rank</th>
      <th class="py-3 px-3 sm:px-4 sticky-col-2 whitespace-nowrap">Participant (${roundMeta.name})</th>
      <th class="py-3 px-3 sm:px-4 text-right whitespace-nowrap">${isRoundActive ? 'Status' : 'Round Points'}</th>
    </tr>
  `;

  const standings = (globalData.round_standings && globalData.round_standings[roundId]) || [];
  let filtered = standings;
  if (filter) {
    filtered = filtered.filter(u => u.username.toLowerCase().includes(filter));
  }

  tableCountLabel.textContent = `Showing ${filtered.length} participants in ${roundMeta.name}`;

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="3" class="text-center py-8 text-slate-500 text-xs">
          No participants found
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(u => {
    let rankBadge = `<span class="font-mono text-slate-400 font-semibold whitespace-nowrap">#${u.rank}</span>`;
    if (u.rank === 1) rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-amber-400 whitespace-nowrap">🥇 1</span>`;
    else if (u.rank === 2) rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-slate-300 whitespace-nowrap">🥈 2</span>`;
    else if (u.rank === 3) rankBadge = `<span class="inline-flex items-center gap-1 font-bold text-amber-600 whitespace-nowrap">🥉 3</span>`;

    const isSelected = selectedUser && selectedUser.toLowerCase() === u.username.toLowerCase();
    let rowClass = 'hover:bg-slate-800/60 cursor-pointer transition active:bg-slate-800/80';
    if (isSelected) rowClass += ' selected-row bg-indigo-900/30 border-l-2 border-indigo-500';

    const rightColDisplay = isRoundActive
      ? '<span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-semibold whitespace-nowrap">Submitted (Pending)</span>'
      : `<span class="font-black text-indigo-400 font-mono text-xs sm:text-sm whitespace-nowrap">${u.score}</span>`;

    return `
      <tr class="${rowClass}" onclick="selectUser('${u.username}')">
        <td class="py-3 px-2 sm:px-3 sticky-col-1 whitespace-nowrap">${rankBadge}</td>
        <td class="py-3 px-3 sm:px-4 sticky-col-2 whitespace-nowrap font-semibold text-white text-xs sm:text-sm hover:underline">${u.username}</td>
        <td class="py-3 px-3 sm:px-4 text-right whitespace-nowrap">${rightColDisplay}</td>
      </tr>
    `;
  }).join('');
}

// ==========================================
// Matches Distribution (Round 6 & Round 5)
// ==========================================
function renderMatchDistributions() {
  if (!globalData) return;

  updateDistTabsUI();

  const roundDistributions = (globalData.round_match_distributions && globalData.round_match_distributions[currentDistRound]) 
    || (currentDistRound === 'r6' ? globalData.match_distributions : []) 
    || [];

  if (!roundDistributions || roundDistributions.length === 0) {
    matchesGrid.innerHTML = `
      <div class="glass-panel rounded-xl p-8 border border-slate-800 col-span-full text-center text-slate-400 text-xs">
        No match predictions data available for this round.
      </div>
    `;
    return;
  }

  matchesGrid.innerHTML = roundDistributions.map((m, idx) => {
    let actualBadge = '';
    if (m.actual) {
      const outcomeNames = { 'Home': 'Home Win (1)', 'Draw': 'Draw (X)', 'Away': 'Away Win (2)' };
      actualBadge = `
        <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1 shrink-0">
          <i data-lucide="check" class="w-3 h-3"></i> Result: ${outcomeNames[m.actual] || m.actual}
        </span>
      `;
    } else {
      actualBadge = `
        <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/80 flex items-center gap-1 shrink-0">
          <i data-lucide="clock" class="w-3 h-3 text-slate-400"></i> Pending Results
        </span>
      `;
    }

    return `
      <div class="glass-panel rounded-xl p-3.5 sm:p-4 border border-slate-800 space-y-2.5 sm:space-y-3">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center space-x-2 min-w-0">
            <span class="text-xs font-mono font-bold text-indigo-400 shrink-0">#${idx + 1}</span>
            <h4 class="text-xs sm:text-sm font-bold text-white truncate">${m.match}</h4>
            <span class="text-[10px] text-slate-500 font-mono shrink-0">(${m.total} votes)</span>
          </div>
          ${actualBadge}
        </div>

        <!-- Segmented Bar -->
        <div class="space-y-1.5">
          <div class="h-2.5 w-full bg-slate-800 rounded-full overflow-hidden flex">
            <div style="width: ${m.home_pct}%" class="bg-blue-500 transition-all duration-500" title="Home: ${m.home_pct}%"></div>
            <div style="width: ${m.draw_pct}%" class="bg-amber-500 transition-all duration-500" title="Draw: ${m.draw_pct}%"></div>
            <div style="width: ${m.away_pct}%" class="bg-violet-500 transition-all duration-500" title="Away: ${m.away_pct}%"></div>
          </div>

          <!-- Labels -->
          <div class="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-400 pt-0.5">
            <div class="flex items-center gap-1">
              <span class="w-2 h-2 rounded-full bg-blue-500"></span>
              <span>1 (${m.home}): <strong class="text-white">${m.home_pct}%</strong></span>
            </div>
            <div class="flex items-center gap-1">
              <span class="w-2 h-2 rounded-full bg-amber-500"></span>
              <span>X (${m.draw}): <strong class="text-white">${m.draw_pct}%</strong></span>
            </div>
            <div class="flex items-center gap-1">
              <span class="w-2 h-2 rounded-full bg-violet-500"></span>
              <span>2 (${m.away}): <strong class="text-white">${m.away_pct}%</strong></span>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  if (window.lucide) lucide.createIcons();
}

function updateDistTabsUI() {
  if (!distTabsContainer) return;
  distTabsContainer.querySelectorAll('.dist-tab-btn').forEach(btn => {
    const round = btn.getAttribute('data-dist-tab');
    if (round === currentDistRound) {
      btn.className = 'dist-tab-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 bg-indigo-600 text-white shadow-sm shadow-indigo-600/30 active:scale-95';
    } else {
      btn.className = 'dist-tab-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700 active:scale-95';
    }
  });
}
