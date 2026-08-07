// Narayana L&D System Main JavaScript

// Theme Initialization & Management
(function () {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
    }
})();

document.addEventListener('DOMContentLoaded', function () {
    // Sync Theme Toggle UI
    updateThemeToggleUI();

    // Attach click listeners to theme toggle buttons
    const themeButtons = document.querySelectorAll('.theme-toggle-btn');
    themeButtons.forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            toggleTheme();
        });
    });

    // Profile Sidebar Expand / Collapse Toggle Handler
    setupSidebarToggle();

    // Dummy Header Tabs View Handler
    setupDummyHeaderTabs();

    // Sidebar toggle handler (Admin mode)
    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function (e) {
            e.preventDefault();
            document.getElementById('wrapper').classList.toggle('toggled');
        });
    }

    // Auto dismiss toasts after 4 seconds
    const toastElList = [].slice.call(document.querySelectorAll('.toast'));
    toastElList.map(function (toastEl) {
        return new bootstrap.Toast(toastEl, { delay: 4000 }).show();
    });

    // Dynamic fields for Live Class (Online vs In Person)
    const classModeSelect = document.getElementById('class_mode');
    if (classModeSelect) {
        function toggleModeFields() {
            const mode = classModeSelect.value;
            const inPersonFields = document.querySelectorAll('.in-person-field');
            const onlineFields = document.querySelectorAll('.online-field');

            if (mode === 'Online') {
                inPersonFields.forEach(el => el.style.display = 'none');
                onlineFields.forEach(el => el.style.display = 'block');
            } else {
                inPersonFields.forEach(el => el.style.display = 'block');
                onlineFields.forEach(el => el.style.display = 'none');
            }
        }
        classModeSelect.addEventListener('change', toggleModeFields);
        toggleModeFields();
    }
});

// Sidebar Expand / Collapse Logic
function setupSidebarToggle() {
    const toggleBtn = document.getElementById('toggleSidebarBtn');
    const toggleFooterBtn = document.getElementById('toggleSidebarFooterBtn');
    const sidebar = document.getElementById('learnerSidebar');
    const sidebarCol = document.getElementById('sidebarCol');
    const mainCol = document.getElementById('mainContentCol');
    const icon = document.getElementById('toggleSidebarIcon');
    const text = document.getElementById('toggleSidebarText');
    const footerText = document.getElementById('toggleSidebarFooterText');

    if (sidebar) {
        function setCollapsedState(collapsed) {
            if (collapsed) {
                sidebar.classList.add('collapsed');
                if (sidebarCol) sidebarCol.className = 'col-lg-1 col-xl-1 sidebar-col';
                if (mainCol) mainCol.className = 'col-lg-8 col-xl-8 main-content-col';
                if (icon) icon.className = 'fa-solid fa-angles-right';
                if (text) text.innerText = '';
                if (footerText) footerText.innerText = 'Expand';
            } else {
                sidebar.classList.remove('collapsed');
                if (sidebarCol) sidebarCol.className = 'col-lg-3 col-xl-2 sidebar-col';
                if (mainCol) mainCol.className = 'col-lg-6 col-xl-7 main-content-col';
                if (icon) icon.className = 'fa-solid fa-angles-left';
                if (text) text.innerText = 'Collapse';
                if (footerText) footerText.innerText = 'Collapse';
            }
        }

        const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
        setCollapsedState(isCollapsed);

        const handleToggle = function (e) {
            e.preventDefault();
            const nextState = !sidebar.classList.contains('collapsed');
            setCollapsedState(nextState);
            localStorage.setItem('sidebar_collapsed', nextState);
        };

        if (toggleBtn) toggleBtn.addEventListener('click', handleToggle);
        if (toggleFooterBtn) toggleFooterBtn.addEventListener('click', handleToggle);
    }
}

// Dummy Header Tabs Handlers
function setupDummyHeaderTabs() {
    const dummyTabs = document.querySelectorAll('.dummy-nav-tab');
    dummyTabs.forEach(tab => {
        tab.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('.ls-nav-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            const tabName = this.getAttribute('data-tab-name') || 'Dummy View';
            showDummyModal(tabName);
        });
    });
}

// Modal View Trigger for Dummy Header Tabs
function showDummyModal(tabName) {
    let existingModal = document.getElementById('dummyTabModal');
    if (existingModal) existingModal.remove();

    const modalHTML = `
    <div class="modal fade" id="dummyTabModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content border-0 shadow-lg rounded-4">
                <div class="modal-header border-0 pb-0">
                    <h5 class="modal-title fw-bold text-dark"><i class="fa-solid fa-layer-group text-primary me-2"></i> ${tabName}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body text-center py-4">
                    <div class="bg-primary-subtle text-primary rounded-circle p-3 d-inline-flex mb-3">
                        <i class="fa-solid fa-laptop-code fs-2"></i>
                    </div>
                    <h6 class="fw-bold text-dark mb-2">${tabName} Preview Panel</h6>
                    <p class="text-muted small mb-0">This tab view is configured as an interactive preview panel for the Narayana L&D Management System.</p>
                </div>
                <div class="modal-footer border-0 pt-0">
                    <button type="button" class="btn btn-primary w-100 fw-bold" data-bs-dismiss="modal">Close View</button>
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const modal = new bootstrap.Modal(document.getElementById('dummyTabModal'));
    modal.show();
}

// Toggle Theme Function
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeToggleUI();
}

// Update Theme Toggle Buttons UI
function updateThemeToggleUI() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeButtons = document.querySelectorAll('.theme-toggle-btn');
    
    themeButtons.forEach(btn => {
        if (currentTheme === 'dark') {
            btn.innerHTML = `<i class="fa-solid fa-sun text-warning me-1"></i> <span>Light Mode</span>`;
            btn.setAttribute('aria-label', 'Switch to Light Theme');
        } else {
            btn.innerHTML = `<i class="fa-solid fa-moon text-primary me-1"></i> <span>Dark Mode</span>`;
            btn.setAttribute('aria-label', 'Switch to Dark Theme');
        }
    });
}

// Dynamic AJAX unlock function for locked Live Classes
function submitUnlockClass(classIdStr) {
    const reasonInput = document.getElementById('unlockReasonInput');
    const reason = reasonInput ? reasonInput.value.trim() : '';

    if (!reason) {
        alert('Mandatory reason for unlocking class must be provided.');
        return;
    }

    const formData = new FormData();
    formData.append('class_id', classIdStr);
    formData.append('reason', reason);

    fetch('/classes/unlock', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(err => {
        alert('Failed to unlock class: ' + err);
    });
}
