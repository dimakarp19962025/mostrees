// Конфигурация
const API_URL = "https://ваш-сервер.com/api";
let map;

// Инициализация карты
function initMap() {
    map = L.map('map').setView([55.751244, 37.618423], 12);
    
    // Слой OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Загрузка деревьев
    loadTrees();
}

// Загрузка деревьев с сервера
async function loadTrees() {
    try {
        const userData = window.Telegram.WebApp.initDataUnsafe.user;
        if (!userData || !userData.id) {
            console.error("User ID not available");
            return;
        }
        
        const response = await fetch(`${API_URL}/trees?user_id=${userData.id}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const trees = await response.json();
        renderTrees(trees);
    } catch (error) {
        console.error("Ошибка загрузки деревьев:", error);
        alert("Не удалось загрузить данные деревьев");
    }
}

// Отображение деревьев на карте
function renderTrees(trees) {
    trees.forEach(tree => {
        const marker = L.marker([tree.lat, tree.lng]).addTo(map);
        
        // Установка иконки в зависимости от статуса
        marker.setIcon(getTreeIcon(tree.status));
        
        // Добавление всплывающего окна для хранителей
        if (isUserGuardian(tree.district)) {
            marker.bindPopup(createTreePopup(tree));
        }
    });
}

// Создание иконки дерева
function getTreeIcon(status) {
    const iconUrl = 'icons/tree-icon.png';
    const icon = L.icon({
        iconUrl: iconUrl,
        iconSize: [32, 32],
        className: status.toLowerCase()
    });
    return icon;
}

// Проверка прав пользователя
function isUserGuardian(district) {
    const userData = window.Telegram.WebApp.initDataUnsafe.user;
    // В реальном приложении нужно запросить данные пользователя с сервера
    return true; // Заглушка для демонстрации
}

// Создание всплывающего окна
function createTreePopup(tree) {
    return `
        <div class="tree-popup">
            <img src="${tree.photos[0]}" alt="Фото дерева">
            <p><strong>Статус:</strong> ${getStatusText(tree.status)}</p>
            <p><strong>Тип:</strong> ${getTypeText(tree.type)}</p>
            <p><strong>Район:</strong> ${tree.district}</p>
            <div class="actions">
                <button onclick="verifyTree('${tree.id}', 'approved')">✅ Одобрить</button>
                <button class="reject" onclick="verifyTree('${tree.id}', 'rejected')">❌ Отклонить</button>
                <button onclick="markAsDuplicate('${tree.id}')">🚫 Дубликат</button>
            </div>
        </div>
    `;
}

// Функции для обработки действий
window.verifyTree = async (treeId, status) => {
    try {
        const userData = window.Telegram.WebApp.initDataUnsafe.user;
        const response = await fetch(`${API_URL}/trees/${treeId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                status,
                user_id: userData.id 
            })
        });
        
        if (response.ok) {
            alert(`Статус дерева обновлен!`);
            location.reload();
        } else {
            alert("Ошибка при обновлении статуса");
        }
    } catch (error) {
        console.error("Ошибка обновления:", error);
        alert("Произошла ошибка");
    }
};

window.markAsDuplicate = async (treeId) => {
    // Аналогично verifyTree
};

// Вспомогательные функции
function getStatusText(status) {
    const statuses = {
        'pending': 'На рассмотрении',
        'approved': 'Одобрено',
        'rejected': 'Отклонено',
        'duplicate': 'Дубликат'
    };
    return statuses[status] || status;
}

function getTypeText(type) {
    const types = {
        'alive': 'Живое дерево',
        'dead': 'Погибшее дерево',
        'attention': 'Требует наблюдения',
        'special': 'Особое наблюдение'
    };
    return types[type] || type;
}

// Инициализация при загрузке
window.Telegram.WebApp.ready();
initMap();
