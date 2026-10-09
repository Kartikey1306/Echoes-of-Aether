using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Sound of the player's car (procedural loops from tools/audio/vehicle_sfx.py): two engine beds crossfaded and
    /// pitched by RPM and load, tyre squeal from the slip, rolling road roar from the speed, the horn while held;
    /// impacts / scrapes / doors are one-shots through the AudioManager. Volumes follow the master and SFX settings,
    /// fall silent while paused, and the engine winds down once nobody is driving. Voices only play while audible.
    /// </summary>
    public sealed class CarAudio : MonoBehaviour
    {
        PlayerCar car;
        AudioSource low, high, skid, road, horn;
        float running, load, scrapeCd;
        /// <summary>Horn held (set by <see cref="Driving"/>).</summary>
        [System.NonSerialized] public bool Horn;

        public void Init(PlayerCar c)
        {
            car = c;
            var root = new GameObject("CarAudio");
            root.transform.SetParent(transform, false);
            root.transform.localPosition = new Vector3(0, 0.6f, 0);
            low = Source(root, "car_engine_low");
            high = Source(root, "car_engine_high");
            skid = Source(root, "car_skid_loop");
            road = Source(root, "car_road_loop");
            horn = Source(root, "car_horn_loop");
        }

        static AudioSource Source(GameObject root, string clip)
        {
            var s = root.AddComponent<AudioSource>();
            s.clip = Resources.Load<AudioClip>("Audio/SFX/" + clip);
            s.loop = true;
            s.playOnAwake = false;
            s.spatialBlend = 0.7f;
            s.rolloffMode = AudioRolloffMode.Logarithmic;
            s.minDistance = 5f;
            s.maxDistance = 70f;
            s.dopplerLevel = 0f;
            s.volume = 0f;
            s.priority = 64;
            return s;
        }

        static float Curve(float v) => Mathf.Clamp01(v) * Mathf.Clamp01(v);

        /// <summary>Bus volume as AudioManager applies it (master x sfx, squared curves).</summary>
        static float Bus()
        {
            var a = G.Settings?.Data?.Audio;
            return a == null ? 0.5f : Curve(a.Master) * Curve(a.Sfx);
        }

        /// <summary>All loop clips found (tests).</summary>
        public bool ClipsLoaded => low != null && low.clip != null && high.clip != null && skid.clip != null && road.clip != null && horn.clip != null;

        /// <summary>Current loop levels (tests / debugging).</summary>
        public string Levels => low == null ? "-" :
            $"low {low.volume:0.00}@{low.pitch:0.00} high {high.volume:0.00}@{high.pitch:0.00} skid {skid.volume:0.00} road {road.volume:0.00}";

        /// <summary>Metal scraping along a wall (rate-limited one-shot).</summary>
        public void Scrape(float k)
        {
            if (scrapeCd > 0f) return;
            scrapeCd = 0.16f;
            G.Audio?.Play("car_scrape", transform.position, 0.35f + 0.65f * k, Random.Range(0.9f, 1.1f));
        }

        void Update()
        {
            if (car == null) return;
            var dt = Time.unscaledDeltaTime;
            scrapeCd -= Time.deltaTime;
            var m = G.Manager;
            var live = m != null && m.Mode == GameMode.Play && !m.Paused;
            running = Mathf.MoveTowards(running, car.Driven ? 1f : 0f, dt * (car.Driven ? 2.5f : 0.9f));
            var bus = live ? Bus() : 0f;
            var rpm = car.Rpm01;
            load = Mathf.Lerp(load, Mathf.Clamp01(Mathf.Max(car.Throttle, car.Reversing ? car.Brake : 0f)), 1f - Mathf.Exp(-dt * 6f));
            var speed = car.Speed;
            var sp01 = Mathf.Clamp01(speed / 45f);
            var xf = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.35f, 0.8f, rpm));
            var eng = running * (0.55f + 0.45f * load);
            Set(low, bus * eng * (1f - xf) * 0.85f, Mathf.Lerp(0.62f, 1.85f, rpm));
            Set(high, bus * eng * xf * 0.75f, Mathf.Lerp(0.55f, 1.32f, rpm));
            var slide = car.Skid * Mathf.Clamp01(speed / 5f);
            Set(skid, bus * slide * 0.7f, 0.9f + 0.18f * car.Skid + 0.1f * sp01);
            Set(road, bus * (car.Parked ? 0f : Mathf.Clamp01(speed / 8f) * (0.22f + 0.5f * sp01)), 0.75f + 0.55f * sp01);
            Set(horn, bus * (Horn && car.Driven ? 0.75f : 0f), 1f);
        }

        static void Set(AudioSource s, float vol, float pitch)
        {
            if (s == null || s.clip == null) return;
            s.volume = Mathf.Clamp01(vol);
            s.pitch = pitch;
            if (vol > 0.002f) { if (!s.isPlaying) s.Play(); }
            else if (s.isPlaying) s.Stop();
        }
    }
}
