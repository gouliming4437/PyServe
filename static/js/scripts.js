document.addEventListener('DOMContentLoaded', function() {
    // Existing keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Alt + H = Home
        if (e.altKey && e.key === 'h') {
            window.location.href = '/';
        }
        // Alt + S = Search focus
        if (e.altKey && e.key === 's') {
            document.querySelector('.search-bar input').focus();
        }
    });

    // Message rotation
    const messages = document.querySelectorAll('.message');
    if (messages.length > 0) {
        let currentIndex = 0;
        messages[0].classList.add('active');

        setInterval(() => {
            messages[currentIndex].classList.remove('active');
            currentIndex = (currentIndex + 1) % messages.length;
            messages[currentIndex].classList.add('active');
        }, 5000);
    }
}); 