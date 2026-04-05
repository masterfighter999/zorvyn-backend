document.addEventListener('DOMContentLoaded', async () => {
    // 1. API Config & Authentication
    const API_BASE = 'http://localhost:8000';
    let token = sessionStorage.getItem('zorvyn_token');
    let currentUserRole = 'viewer';

    if (!token) {
        if (!window.location.pathname.includes('login.html')) {
            window.location.href = 'login.html';
        }
        return;
    }

    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        currentUserRole = payload.role || 'viewer';
        
        let userName = payload.name || 'Zorvyn User';
        if (payload.sub === '1' && payload.role === 'admin' && !payload.name) {
            userName = 'Darlene Robertson (Admin)';
        }

        const headerName = document.getElementById('user-header-name');
        if (headerName) headerName.textContent = userName;

        const headerRole = document.getElementById('user-header-role');
        if (headerRole) headerRole.textContent = currentUserRole;

        const profileImg = document.getElementById('user-profile-img');
        if (profileImg) {
            profileImg.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(userName)}&background=8b5cf6&color=fff`;
            profileImg.style.display = 'block';
        }

    } catch(e) {
        console.error("Invalid token format");
    }

    // 2. UI Access Control
    const navRecords = document.querySelector('[data-view="records"]');
    const navUsers = document.getElementById('nav-users');
    const newRecordBtn = document.getElementById('btn-new-record');
    const chartTransactions = document.getElementById('chart-card-transactions');
    const chartNetIncome = document.getElementById('chart-card-net-income');

    if (currentUserRole === 'viewer') {
        // Viewers: hide Records tab and chart sections entirely
        if (navRecords) navRecords.style.display = 'none';
        if (chartTransactions) chartTransactions.style.display = 'none';
        if (chartNetIncome) chartNetIncome.style.display = 'none';
    }

    if (currentUserRole === 'admin') {
        if (navUsers) navUsers.style.display = 'flex';
        if (newRecordBtn) newRecordBtn.style.display = 'block';
    }

    // 3. Helpers
    const formatCurrency = (value) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency', currency: 'USD', maximumFractionDigits: 0
        }).format(value);
    };

    function showNotification(message, type = 'info') {
        const existing = document.getElementById('zorvyn-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'zorvyn-toast';
        toast.textContent = message;
        Object.assign(toast.style, {
            position: 'fixed', bottom: '1.5rem', right: '1.5rem',
            padding: '0.85rem 1.25rem', borderRadius: '10px',
            fontFamily: 'inherit', fontSize: '0.9rem', color: '#fff',
            background: type === 'error' ? '#dc2626' : '#8b5cf6',
            boxShadow: '0 4px 20px rgba(0,0,0,0.35)', zIndex: 9999,
            opacity: '0', transition: 'opacity 0.25s ease',
        });
        document.body.appendChild(toast);
        requestAnimationFrame(() => { toast.style.opacity = '1'; });
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    async function fetchData(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers
        };
        const fetchOptions = { cache: 'no-store', ...options, headers };
        const response = await fetch(url, fetchOptions);
        if (!response.ok) {
            const err = await response.json().catch(()=>({}));
            throw new Error(err.detail || `HTTP error! status: ${response.status}`);
        }
        if (response.status === 204) return null;
        return await response.json();
    }

    // 4. SPA Routing
    const views = ['dashboard', 'records', 'users'];
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const viewId = e.currentTarget.getAttribute('data-view');
            if(viewId) {
                e.preventDefault();
                switchView(viewId);
            }
        });
    });

    function switchView(viewId) {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        const activeNav = document.querySelector(`[data-view="${viewId}"]`);
        if(activeNav) activeNav.classList.add('active');

        views.forEach(v => {
            const el = document.getElementById(`view-${v}`);
            if(el) el.style.display = (v === viewId) ? 'block' : 'none';
        });

        if (viewId === 'dashboard') loadDashboard();
        if (viewId === 'records') loadRecords();
        if (viewId === 'users') loadUsers();
    }

    // ==========================================
    // 5. DASHBOARD LOGIC
    // ==========================================
    let chartInstance = null;
    let progressChartInstance = null;
    
    // Store current trend settings so dashboard reloads preserve them
    let currentTrendPeriod = 'quarter';
    let currentTrendCount = 4;
    
    async function loadDashboard() {
        try {
            const summaryData = await fetchData(`${API_BASE}/dashboard/summary`);
            
            const incomeEl  = document.getElementById('total-income');
            const expenseEl = document.getElementById('total-expense');
            const balanceEl = document.getElementById('net-balance');
            const usersEl = document.getElementById('total-users');

            if (incomeEl)  incomeEl.innerText  = formatCurrency(summaryData.total_income);
            if (expenseEl) expenseEl.innerText = formatCurrency(summaryData.total_expense);
            if (balanceEl) balanceEl.innerText = formatCurrency(summaryData.net_balance);

            const formatTrend = (val, invertColors = false) => {
                if (val === undefined || val === null) return { text: 'N/A', class: '' };
                const isPositive = val >= 0;
                const sign = isPositive ? '+' : '';
                let className = 'positive';
                if ((isPositive && invertColors) || (!isPositive && !invertColors)) {
                    className = 'negative';
                }
                return { text: `${sign}${val.toFixed(1)}% from last month`, class: className };
            };

            const incTrendEl = document.getElementById('income-trend');
            if (incTrendEl && summaryData.income_trend !== undefined) {
                const t = formatTrend(summaryData.income_trend, false);
                incTrendEl.textContent = t.text;
                incTrendEl.className = `card-change ${t.class}`;
            }

            const expTrendEl = document.getElementById('expense-trend');
            if (expTrendEl && summaryData.expense_trend !== undefined) {
                const t = formatTrend(summaryData.expense_trend, true);
                expTrendEl.textContent = t.text;
                expTrendEl.className = `card-change ${t.class}`;
            }

            const balTrendEl = document.getElementById('balance-trend');
            if (balTrendEl && summaryData.balance_trend !== undefined) {
                const t = formatTrend(summaryData.balance_trend, false);
                balTrendEl.textContent = t.text;
                balTrendEl.className = `card-change ${t.class}`;
            }

            // Trends and charts are only for analysts and admins
            if (currentUserRole !== 'viewer') {
                await loadTrends(currentTrendPeriod, currentTrendCount);
                await loadMeanBalance();
            }
        } catch (e) {
            console.error('Failed to load dashboard', e);
            showNotification('Could not load dashboard data', 'error');
        }
    }

    async function loadTrends(period, count) {
        try {
            const trendsData = await fetchData(`${API_BASE}/dashboard/trends?period=${period}&count=${count}`);
            initChart(trendsData);
        } catch (e) {
            console.error('Failed to load trends data', e);
            showNotification('Could not load trends data', 'error');
            initChart([]); // render empty placeholder/error chart
        }
    }

    async function loadMeanBalance() {
        try {
            const currentYear = new Date().getFullYear();
            // Fetch perfectly 12 months ending in Dec of currentYear
            const data = await fetchData(`${API_BASE}/dashboard/trends?period=month&count=12&end_date=${currentYear}-12-31`);
            initMeanBalanceChart(data);
        } catch (e) {
            console.error('Failed to load net income trend data', e);
            initMeanBalanceChart([]);
        }
    }

    const btnQuarterly = document.getElementById('btn-chart-quarterly');
    const btnSemi = document.getElementById('btn-chart-semi');
    const btnAnnually = document.getElementById('btn-chart-annually');

    function resetChartButtons() {
        if (btnQuarterly) {
            btnQuarterly.classList.remove('active');
            btnQuarterly.setAttribute('aria-pressed', 'false');
        }
        if (btnSemi) {
            btnSemi.classList.remove('active');
            btnSemi.setAttribute('aria-pressed', 'false');
        }
        if (btnAnnually) {
            btnAnnually.classList.remove('active');
            btnAnnually.setAttribute('aria-pressed', 'false');
        }
    }

    if (btnQuarterly && btnSemi && btnAnnually) {
        btnQuarterly.addEventListener('click', () => {
            resetChartButtons();
            btnQuarterly.classList.add('active');
            btnQuarterly.setAttribute('aria-pressed', 'true');
            currentTrendPeriod = 'quarter'; currentTrendCount = 4;
            loadTrends('quarter', 4);
        });
        btnSemi.addEventListener('click', () => {
            resetChartButtons();
            btnSemi.classList.add('active');
            btnSemi.setAttribute('aria-pressed', 'true');
            currentTrendPeriod = 'month'; currentTrendCount = 6;
            loadTrends('month', 6);
        });
        btnAnnually.addEventListener('click', () => {
            resetChartButtons();
            btnAnnually.classList.add('active');
            btnAnnually.setAttribute('aria-pressed', 'true');
            currentTrendPeriod = 'year'; currentTrendCount = 3;
            loadTrends('year', 3);
        });
    }

    function initChart(trendsData) {
        const ctx = document.getElementById('engagementChart');
        if (!ctx) return;
        
        if (chartInstance) {
            chartInstance.destroy();
        }

        const labels = trendsData.map(d => {
            // period could be "2024-03", "Q1 2024", or "2024"
            if (d.period.includes('-')) {
                const [year, month] = d.period.split('-');
                return new Date(year, month - 1).toLocaleString('default', { month: 'short' });
            }
            return d.period;
        });
        const incomeValues = trendsData.map(d => parseFloat(d.income));
        const expenseValues = trendsData.map(d => parseFloat(d.expense));
        const netValues = trendsData.map(d => parseFloat(d.income) - parseFloat(d.expense));

        // Income gradient
        const incGradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
        incGradient.addColorStop(0, 'rgba(16, 185, 129, 1)'); 
        incGradient.addColorStop(1, 'rgba(16, 185, 129, 0.2)');

        // Expense gradient
        const expGradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
        expGradient.addColorStop(0, 'rgba(239, 68, 68, 1)'); 
        expGradient.addColorStop(1, 'rgba(239, 68, 68, 0.2)');

        // Net line color
        const netColor = 'rgba(139, 92, 246, 1)';

        chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Net Income', 
                        data: netValues,
                        type: 'line',
                        borderColor: netColor,
                        backgroundColor: netColor,
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 4
                    },
                    {
                        label: 'Income', 
                        data: incomeValues,
                        backgroundColor: incGradient,
                        borderRadius: 6, 
                        barPercentage: 0.6
                    },
                    {
                        label: 'Expense', 
                        data: expenseValues,
                        backgroundColor: expGradient,
                        borderRadius: 6, 
                        barPercentage: 0.6
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { 
                    legend: { 
                        display: true,
                        labels: { color: 'rgba(255, 255, 255, 0.7)' }
                    } 
                },
                scales: {
                    y: { 
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: 'rgba(255, 255, 255, 0.5)' }
                    },
                    x: { 
                        grid: { display: false },
                        ticks: { color: 'rgba(255, 255, 255, 0.5)' }
                    }
                }
            }
        });
    }

    function initMeanBalanceChart(trendsData) {
        const labels = trendsData.map(d => {
            if (d.period.includes('-')) {
                const [year, month] = d.period.split('-');
                return new Date(year, month - 1).toLocaleString('default', { month: 'short' });
            }
            return d.period;
        });
        const netValues = trendsData.map(d => parseFloat(d.income) - parseFloat(d.expense));

        // Update Net Income Trend header: show total net income for the year
        const totalNetIncome = netValues.reduce((a, b) => a + b, 0);
        const netIncomeEl = document.getElementById('mean-balance-value');
        if (netIncomeEl) {
            netIncomeEl.textContent = netValues.length > 0 ? formatCurrency(totalNetIncome) : '$0';
        }
        // Set the year label (e.g. "2026")
        const yearLabelEl = document.getElementById('net-income-year-label');
        if (yearLabelEl) {
            yearLabelEl.textContent = new Date().getFullYear();
        }

        const progressCtx = document.getElementById('monthlyProgressChart');
        if (progressCtx) {
            if (progressChartInstance) progressChartInstance.destroy();

            const progressColor = '#bef264'; // UI matching lime/yellow

            progressChartInstance = new Chart(progressCtx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Net Balance',
                            data: netValues,
                            borderColor: progressColor,
                            backgroundColor: progressColor,
                            borderWidth: 3,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#1a1a1a',
                            pointBorderColor: progressColor,
                            pointBorderWidth: 2,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { 
                            display: true,
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { 
                                color: 'rgba(255, 255, 255, 0.5)',
                                callback: function(value) {
                                    return Math.abs(value) >= 1000 ? (value/1000) + 'k' : value;
                                }
                            }
                        },
                        x: { 
                            display: true,
                            grid: { display: false },
                            ticks: { color: 'rgba(255, 255, 255, 0.5)', font: { size: 10 } }
                        }
                    },
                    layout: { padding: { top: 10, bottom: 0, left: 10, right: 10 } }
                }
            });
        }
    }

    // ==========================================
    // 6. RECORDS LOGIC
    // ==========================================
    let currentRecords = [];

    async function loadRecords() {
        try {
            const typeFilter = document.getElementById('filter-type')?.value;
            const monthFilter = document.getElementById('filter-month')?.value;
            const sortFilter = document.getElementById('sort-by')?.value;

            let url = `${API_BASE}/records?limit=50`;
            if (typeFilter) url += `&type=${typeFilter}`;

            if (monthFilter) {
                // monthFilter format: YYYY-MM
                const [year, month] = monthFilter.split('-');
                const firstDay = `${year}-${month}-01`;
                // Get the last day of the month by rolling over to day 0 of next month
                const lastDay = new Date(year, month, 0).getDate();
                const lastDayStr = `${year}-${month}-${lastDay}`;
                url += `&from=${firstDay}&to=${lastDayStr}`;
            }

            currentRecords = await fetchData(url);

            // Client-side sorting
            if (sortFilter) {
                currentRecords.sort((a, b) => {
                    if (sortFilter === 'date-desc') return new Date(b.date) - new Date(a.date);
                    if (sortFilter === 'date-asc') return new Date(a.date) - new Date(b.date);
                    if (sortFilter === 'amount-desc') return parseFloat(b.amount) - parseFloat(a.amount);
                    if (sortFilter === 'amount-asc') return parseFloat(a.amount) - parseFloat(b.amount);
                    return 0;
                });
            }

            renderRecords(currentRecords);
        } catch(e) {
            showNotification('Failed to load records', 'error');
        }
    }

    function renderRecords(records) {
        const tbody = document.getElementById('records-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        records.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${r.date}</td>
                <td>${r.category}</td>
                <td>${r.description || ''}</td>
                <td class="type-${r.type}">${r.type}</td>
                <td>${formatCurrency(r.amount)}</td>
                <td>
                    ${currentUserRole === 'admin' ? `
                    <button class="btn-small" onclick="window.appEditRecord(${r.id})">Edit</button>
                    <button class="btn-danger" onclick="window.appDeleteRecord(${r.id})">Del</button>
                    ` : '-'}
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    if (document.getElementById('btn-apply-filters')) {
        document.getElementById('btn-apply-filters').addEventListener('click', loadRecords);
    }

    // Global Functions for inline buttons
    window.appEditRecord = (id) => {
        const rec = currentRecords.find(r => r.id === id);
        if (rec) openRecordModal(rec);
    };

    window.appDeleteRecord = async (id) => {
        if(!confirm('Are you sure you want to delete this record?')) return;
        try {
            await fetchData(`${API_BASE}/records/${id}`, { method: 'DELETE' });
            showNotification('Record deleted successfully');
            addNotification(`Deleted a financial record`);
            loadRecords();
        } catch(e) {
            showNotification(e.message, 'error');
        }
    };

    // ==========================================
    // 7. USERS LOGIC
    // ==========================================
    let currentUsers = [];
    async function loadUsers() {
        if(currentUserRole !== 'admin') return;
        try {
            currentUsers = await fetchData(`${API_BASE}/users`);
            renderUsers(currentUsers);
        } catch(e) {
            showNotification(e.message, 'error');
        }
    }

    function renderUsers(users) {
        const tbody = document.getElementById('users-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        users.forEach(u => {
            const joined = new Date(u.created_at).toLocaleDateString();
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${u.name}</td>
                <td>${u.email}</td>
                <td><span class="role-badge role-${u.role}">${u.role}</span></td>
                <td><span class="status-${u.status}">${u.status}</span></td>
                <td>${joined}</td>
                <td>
                    ${currentUserRole === 'admin' ? `
                    <button class="btn-small" onclick="window.appEditUser(${u.id})">Manage</button>
                    ` : '-'}
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    window.appEditUser = (id) => {
        const user = currentUsers.find(u => u.id === id);
        if (user) openUserModal(user);
    };

    // ==========================================
    // 8. MODAL LOGIC
    // ==========================================
    const modal = document.getElementById('global-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const btnSubmitModal = document.getElementById('btn-submit-modal');
    let submitAction = null;

    if (modal) {
        document.getElementById('btn-close-modal').onclick = () => modal.style.display = 'none';
        document.getElementById('btn-cancel-modal').onclick = () => modal.style.display = 'none';
        btnSubmitModal.onclick = async () => {
            if (submitAction) await submitAction();
        };

        if (document.getElementById('btn-new-record')) {
            document.getElementById('btn-new-record').onclick = () => openRecordModal();
        }
    }

    function openRecordModal(record = null) {
        modalTitle.textContent = record ? 'Edit Record' : 'New Record';
        modalBody.innerHTML = `
            <div class="modal-form">
                <div class="form-group">
                    <label>Amount</label>
                    <input type="number" id="rec-amount" step="0.01" value="${record ? record.amount : ''}">
                </div>
                <div class="form-group">
                    <label>Type</label>
                    <select id="rec-type">
                        <option value="income" ${record?.type === 'income' ? 'selected' : ''}>Income</option>
                        <option value="expense" ${record?.type === 'expense' ? 'selected' : ''}>Expense</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Category</label>
                    <input type="text" id="rec-category" value="${record ? record.category : ''}">
                </div>
                <div class="form-group">
                    <label>Date</label>
                    <input type="date" id="rec-date" value="${record ? record.date : new Date().toISOString().split('T')[0]}">
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="rec-desc">${record ? (record.description || '') : ''}</textarea>
                </div>
            </div>
        `;
        modal.style.display = 'flex';

        submitAction = async () => {
            const body = {
                amount: parseFloat(document.getElementById('rec-amount').value),
                type: document.getElementById('rec-type').value,
                category: document.getElementById('rec-category').value,
                date: document.getElementById('rec-date').value,
                description: document.getElementById('rec-desc').value
            };
            try {
                if (record) {
                    await fetchData(`${API_BASE}/records/${record.id}`, { method: 'PATCH', body: JSON.stringify(body) });
                    addNotification(`Updated record for ${formatCurrency(body.amount)} (${body.category})`);
                } else {
                    await fetchData(`${API_BASE}/records`, { method: 'POST', body: JSON.stringify(body) });
                    addNotification(`Created new ${body.type} record: ${formatCurrency(body.amount)}`);
                }
                showNotification(record ? 'Record updated' : 'Record created');
                modal.style.display = 'none';
                loadRecords(); // Refresh
                if (document.querySelector('[data-view="dashboard"]').classList.contains('active')) {
                    loadDashboard(); // Refresh dash if visible
                }
            } catch(e) {
                showNotification(e.message, 'error');
            }
        };
    }

    function openUserModal(user) {
        modalTitle.textContent = `Manage User: ${user.name}`;
        modalBody.innerHTML = `
            <div class="modal-form">
                <div class="form-group">
                    <label>Role ${user.email === 'admin@zorvyn.com' ? '(Cannot demote default admin)' : ''}</label>
                    <select id="usr-role" ${user.email === 'admin@zorvyn.com' ? 'disabled' : ''}>
                        <option value="viewer" ${user.role === 'viewer' ? 'selected' : ''}>Viewer</option>
                        <option value="analyst" ${user.role === 'analyst' ? 'selected' : ''}>Analyst</option>
                        <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Status</label>
                    <select id="usr-status">
                        <option value="active" ${user.status === 'active' ? 'selected' : ''}>Active</option>
                        <option value="inactive" ${user.status === 'inactive' ? 'selected' : ''}>Inactive</option>
                    </select>
                </div>
            </div>
        `;
        modal.style.display = 'flex';

        submitAction = async () => {
            const body = {
                role: document.getElementById('usr-role').value,
                status: document.getElementById('usr-status').value
            };
            try {
                await fetchData(`${API_BASE}/users/${user.id}`, { method: 'PATCH', body: JSON.stringify(body) });
                showNotification('User updated successfully');
                modal.style.display = 'none';
                loadUsers(); // Refresh
            } catch(e) {
                showNotification(e.message, 'error');
            }
        };
    }

    // Initialize first view
    switchView('dashboard');

    // 9. LOGOUT LOGIC
    const btnLogout = document.getElementById('btn-logout');
    if (btnLogout) {
        btnLogout.addEventListener('click', () => {
            sessionStorage.removeItem('zorvyn_token');
            window.location.href = 'login.html';
        });
    }

    // 10. DROPDOWNS & NOTIFICATIONS
    const profileToggle = document.getElementById('profile-toggle');
    const profileMenu = document.getElementById('profile-menu');
    const notifyToggle = document.getElementById('btn-notifications-toggle');
    const notifyMenu = document.getElementById('notifications-menu');
    const notifyDot = document.getElementById('notify-dot');
    const notifyList = document.getElementById('notifications-list');

    let sessionNotifications = [];

    // Toggle logic
    function closeAllDropdowns() {
        if(profileMenu) profileMenu.style.display = 'none';
        if(notifyMenu) notifyMenu.style.display = 'none';
    }

    if (profileToggle && profileMenu) {
        profileToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isVisible = profileMenu.style.display === 'block';
            closeAllDropdowns();
            if (!isVisible) profileMenu.style.display = 'block';
        });
    }

    if (notifyToggle && notifyMenu) {
        notifyToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isVisible = notifyMenu.style.display === 'block';
            closeAllDropdowns();
            if (!isVisible) {
                notifyMenu.style.display = 'block';
                if(notifyDot) notifyDot.style.display = 'none'; // mark read
            }
        });
    }

    document.addEventListener('click', closeAllDropdowns);

    // Notification Logic
    function addNotification(message) {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        sessionNotifications.unshift({ message, time });
        
        if (notifyDot) notifyDot.style.display = 'block'; // Show red dot
        
        renderNotifications();
    }

    function renderNotifications() {
        if (!notifyList) return;
        if (sessionNotifications.length === 0) {
            notifyList.innerHTML = '<div class="no-notifications">No new notifications</div>';
            return;
        }

        notifyList.innerHTML = sessionNotifications.map(n => `
            <div class="notification-item">
                <div>${n.message}</div>
                <div class="notification-time">${n.time}</div>
            </div>
        `).join('');
    }

});
