// Campus Recruitment Portal - Interactive Main Scripts

document.addEventListener("DOMContentLoaded", function () {
    // 1. Password Visibility Toggle
    const togglePasswordBtns = document.querySelectorAll(".toggle-password-btn");
    togglePasswordBtns.forEach(btn => {
        btn.addEventListener("click", function () {
            const targetId = this.getAttribute("data-target") || "password";
            const input = document.getElementById(targetId);
            if (input) {
                if (input.type === "password") {
                    input.type = "text";
                    this.innerHTML = '<i class="bi bi-eye-slash"></i>';
                } else {
                    input.type = "password";
                    this.innerHTML = '<i class="bi bi-eye"></i>';
                }
            }
        });
    });

    // 2. Avatar File Input Live Preview
    const avatarFileInput = document.getElementById("avatarFileInput");
    const avatarPreviewImg = document.getElementById("avatarPreviewImg");
    if (avatarFileInput && avatarPreviewImg) {
        avatarFileInput.addEventListener("change", function () {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    avatarPreviewImg.src = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // 3. Preset Avatar Click Handlers
    const presetOptions = document.querySelectorAll(".preset-avatar-option");
    const profilePicField = document.getElementById("profilePicInput");
    presetOptions.forEach(opt => {
        opt.addEventListener("click", function () {
            presetOptions.forEach(o => o.classList.remove("active"));
            this.classList.add("active");
            const avatarUrl = this.getAttribute("data-avatar-url");
            if (avatarPreviewImg) {
                avatarPreviewImg.src = avatarUrl;
            }
            if (profilePicField) {
                profilePicField.value = avatarUrl;
            }
        });
    });

    // 4. Dynamic Avatar Fetch on Email Input in Login Page
    const loginEmailInput = document.getElementById("loginEmail");
    if (loginEmailInput && avatarPreviewImg) {
        let debounceTimer;
        loginEmailInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            const email = this.value.trim();
            if (email.includes("@") && email.length > 4) {
                debounceTimer = setTimeout(() => {
                    fetch(`/api/user-avatar?email=${encodeURIComponent(email)}`)
                        .then(res => res.json())
                        .then(data => {
                            if (data.avatar) {
                                avatarPreviewImg.src = data.avatar;
                            }
                        })
                        .catch(() => {});
                }, 350);
            }
        });
    }

    // 5. Quick Demo Account Fillers
    window.fillDemo = function (role) {
        const emailInput = document.getElementById("loginEmail");
        const passwordInput = document.getElementById("password");
        if (!emailInput || !passwordInput) return;

        if (role === 'student') {
            emailInput.value = 'student@campus.com';
            passwordInput.value = 'student123';
            if (avatarPreviewImg) {
                avatarPreviewImg.src = 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80';
            }
        } else if (role === 'company') {
            emailInput.value = 'google@campus.com';
            passwordInput.value = 'recruiter123';
            if (avatarPreviewImg) {
                avatarPreviewImg.src = 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/google/google-original.svg';
            }
        } else if (role === 'admin') {
            emailInput.value = 'admin@campus.com';
            passwordInput.value = 'admin123';
            if (avatarPreviewImg) {
                avatarPreviewImg.src = 'https://api.dicebear.com/7.x/bottts/svg?seed=admin';
            }
        }
    };

    // 6. Real-Time Live Job Search & Filter on Input
    const searchInput = document.getElementById("jobSearchInput");
    const jobCards = document.querySelectorAll(".job-item-col");
    const counterElem = document.getElementById("drivesCounter");
    const noResultsElem = document.getElementById("liveNoResults");

    if (searchInput && jobCards.length > 0) {
        searchInput.addEventListener("input", function () {
            const query = this.value.toLowerCase().trim();
            let matchCount = 0;

            jobCards.forEach(card => {
                const text = card.textContent.toLowerCase();
                if (!query || text.includes(query)) {
                    card.style.display = "";
                    matchCount++;
                } else {
                    card.style.display = "none";
                }
            });

            if (counterElem) {
                counterElem.textContent = matchCount;
            }

            if (noResultsElem) {
                if (matchCount === 0 && query !== "") {
                    noResultsElem.style.display = "block";
                } else {
                    noResultsElem.style.display = "none";
                }
            }
        });
    }
});
