plugins { id("com.android.application"); id("org.jetbrains.kotlin.android"); id("org.jetbrains.kotlin.plugin.compose") }
android {
 namespace="ai.danisuarez.radar"; compileSdk=35
 defaultConfig { applicationId="ai.danisuarez.radar"; minSdk=26; targetSdk=35; versionCode=1; versionName="0.1.0-rc1" }
 buildFeatures { compose=true; buildConfig=true }
 buildTypes {
  debug { buildConfigField("boolean","REAL_TRADING","false") }
  release { isMinifyEnabled=true; buildConfigField("boolean","REAL_TRADING","false"); proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"),"proguard-rules.pro") }
 }
}
dependencies {
 implementation(platform("androidx.compose:compose-bom:2024.10.01"))
 implementation("androidx.activity:activity-compose:1.9.3")
 implementation("androidx.compose.material3:material3")
 implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
}
