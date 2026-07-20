<input type="text" id="search" placeholder="ابحث في ويكيبيديا">
<button onclick="searchWiki()">بحث</button>

<div id="results"></div>

<script>
async function searchWiki() {
    const query = document.getElementById("search").value;

    const url = `https://ar.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(query)}&limit=10&namespace=0&format=json&origin=*`;

    const response = await fetch(url);
    const data = await response.json();

    let html = "";

    for (let i = 0; i < data[1].length; i++) {
        html += `
            <div style="margin:10px;padding:10px;border:1px solid #ccc;">
                <h3>${data[1][i]}</h3>
                <p>${data[2][i]}</p>
                <a href="${data[3][i]}" target="_blank">فتح المقال</a>
            </div>
        `;
    }

    document.getElementById("results").innerHTML = html;
}
</script>
