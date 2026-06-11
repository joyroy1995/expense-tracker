const expenseForm = document.getElementById('expenseForm');
const descriptionInput = document.getElementById('description');
const preview = document.getElementById('preview');
const toast = document.getElementById('toast');

let predictTimeout;
let userModifiedPreview = false;

if (descriptionInput) {
    descriptionInput.addEventListener('input', (e) => {
        clearTimeout(predictTimeout);
        userModifiedPreview = false;
        const value = e.target.value.trim();

        if (value.length < 2) {
            preview.innerHTML = '';
            return;
        }

        predictTimeout = setTimeout(() => {
            predictExpense(value);
        }, 600);
    });
}

function buildCategoryOptions(selectedCategory) {
    const categories = Object.keys(categoryColors);
    return categories.map(cat =>
        `<option value="${cat}" ${cat === selectedCategory ? 'selected' : ''}>${cat}</option>`
    ).join('');
}

async function predictExpense(description) {
    try {
        const response = await fetch('/api/predict_expense', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description })
        });
        const data = await response.json();

        if (data.category && preview) {
            const catColor = data.color || categoryColors[data.category] || '#6b7280';
            preview.innerHTML = `
                <div class="preview-card editable-preview">
                    <div class="preview-field">
                        <label class="preview-field-label">Category</label>
                        <select class="preview-category-select" style="border-color: ${catColor}40;">
                            ${buildCategoryOptions(data.category)}
                        </select>
                    </div>
                    <div class="preview-field preview-amount-field">
                        <label class="preview-field-label">Amount (৳)</label>
                        <div class="preview-amount-input-wrap">
                            <span class="preview-currency-sign">৳</span>
                            <input type="number" class="preview-amount-input" step="0.01" min="0" value="${data.amount.toFixed(2)}">
                        </div>
                    </div>
                </div>
            `;
            preview.querySelectorAll('select, input').forEach(el => {
                el.addEventListener('change', () => { userModifiedPreview = true; });
                el.addEventListener('input', () => { userModifiedPreview = true; });
            });
        }
    } catch (error) {
        console.error('Prediction error:', error);
    }
}

function getPreviewValues() {
    const catSelect = preview.querySelector('.preview-category-select');
    const amtInput = preview.querySelector('.preview-amount-input');
    if (catSelect && amtInput) {
        return {
            category: catSelect.value,
            amount: parseFloat(amtInput.value) || 0
        };
    }
    return null;
}

function getTodayStr() {
    return new Date().toISOString().split('T')[0];
}

if (expenseForm) {
    expenseForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const submitBtn = document.getElementById('submitBtn');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');

        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'flex';

        const formData = {
            date: document.getElementById('date').value,
            description: document.getElementById('description').value
        };

        const previewValues = getPreviewValues();
        if (previewValues) {
            formData.category = previewValues.category;
            formData.amount = previewValues.amount;
        }

        try {
            const response = await fetch('/api/add_expense', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            if (response.ok) {
                showToast('Expense added!', 'success');
                expenseForm.reset();
                preview.innerHTML = '';
                userModifiedPreview = false;

                if (data.date === getTodayStr()) {
                    addExpenseToList(data);
                    updateTodayTotal(data.amount);
                } else {
                    setTimeout(() => location.reload(), 800);
                }
            } else {
                showToast(data.error || 'Failed to add expense', 'error');
            }
        } catch (error) {
            showToast('Network error. Please try again.', 'error');
        } finally {
            submitBtn.disabled = false;
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
        }
    });
}

function addExpenseToList(expense) {
    const todayExpenses = document.getElementById('todayExpenses');
    const emptyState = todayExpenses.querySelector('.empty-state');

    if (emptyState) {
        emptyState.remove();
    }

    const expenseItem = document.createElement('div');
    expenseItem.className = 'expense-item';
    expenseItem.dataset.id = expense.id;
    expenseItem.innerHTML = `
        <div class="expense-info">
            <div class="expense-description">${expense.description}</div>
            <span class="category-badge" style="background-color: ${expense.color}">
                ${expense.category}
            </span>
        </div>
        <div class="expense-actions">
            <span class="expense-amount">৳${expense.amount.toFixed(2)}</span>
            <button class="btn-delete" onclick="deleteExpense(${expense.id})">&times;</button>
        </div>
    `;

    todayExpenses.insertBefore(expenseItem, todayExpenses.firstChild);
}

function updateTodayTotal(amount) {
    const totalEl = document.querySelector('.stats-grid .stat-card:first-child .stat-value');
    if (totalEl) {
        const current = parseFloat(totalEl.textContent.replace(/[৳,]/g, '')) || 0;
        const newTotal = current + amount;
        totalEl.textContent = `৳${newTotal.toFixed(2)}`;
    }

    const countEl = document.querySelector('.stats-grid .stat-card:last-child .stat-value');
    if (countEl) {
        countEl.textContent = parseInt(countEl.textContent) + 1;
    }
}

async function deleteExpense(id) {
    if (!confirm('Delete this expense?')) return;

    try {
        const response = await fetch(`/api/delete_expense/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('Expense deleted', 'success');
            const element = document.querySelector(`[data-id="${id}"]`);
            if (element) {
                const amount = parseFloat(element.querySelector('.expense-amount').textContent.replace(/[৳,]/g, ''));
                updateTodayTotal(-amount);
                element.style.opacity = '0';
                element.style.transform = 'translateX(-10px)';
                setTimeout(() => element.remove(), 300);
            }
        } else {
            showToast('Failed to delete expense', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
}

function showToast(message, type = 'success') {
    if (!toast) return;

    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function changePeriod() {
    const year = document.getElementById('yearSelect').value;
    const month = document.getElementById('monthSelect').value;
    window.location.href = `/dashboard?year=${year}&month=${parseInt(month)}`;
}

if (typeof categoryTotals !== 'undefined' && typeof categoryColors !== 'undefined') {
    initCharts();
}

function initCharts() {
    const categoryCtx = document.getElementById('categoryChart');
    const monthlyCtx = document.getElementById('monthlyChart');

    if (categoryCtx && categoryTotals && categoryTotals.length > 0) {
        const labels = categoryTotals.map(c => c.category);
        const data = categoryTotals.map(c => c.total);
        const colors = labels.map(l => categoryColors[l] || '#6b7280');

        new Chart(categoryCtx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data,
                    backgroundColor: colors,
                    borderWidth: 0,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 10,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ৳${value.toFixed(2)} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    if (monthlyCtx && monthlyTotals && monthlyTotals.length > 0) {
        const sorted = [...monthlyTotals].reverse();
        const labels = sorted.map(m => {
            const [year, month] = m.month.split('-');
            const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            return `${monthNames[parseInt(month) - 1]} ${year}`;
        });
        const data = sorted.map(m => m.total);

        new Chart(monthlyCtx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Monthly Total',
                    data,
                    backgroundColor: '#6366f1',
                    borderRadius: 6,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => `৳${context.parsed.y.toFixed(2)}`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => `৳${value}`
                        },
                        grid: {
                            color: '#f1f5f9'
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }
}
