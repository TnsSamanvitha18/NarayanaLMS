document.addEventListener('DOMContentLoaded', function () {
    // Sidebar toggle handler
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
