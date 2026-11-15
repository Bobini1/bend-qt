namespace ProtectedFieldBits {
struct Mask {
    size_t first = 0;
    unsigned width = 0;
    uint64_t maximum() const { return width == 64 ? ~uint64_t(0) : (uint64_t(1) << width) - 1; }
    template<class T> uint64_t decodedMaximum() const {
        if constexpr (std::is_signed_v<T>) return ~uint64_t(0);
        return maximum();
    }
    uint64_t read(const void *object) const {
        const auto *bytes = static_cast<const unsigned char *>(object);
        uint64_t result = 0;
        for (unsigned bit = 0; bit < width; ++bit) {
            const size_t position = first + bit;
            result |= uint64_t((bytes[position / CHAR_BIT] >> (position % CHAR_BIT)) & 1) << bit;
        }
        return result;
    }
    void write(void *object, uint64_t value) const {
        auto *bytes = static_cast<unsigned char *>(object);
        for (unsigned bit = 0; bit < width; ++bit) {
            const size_t position = first + bit;
            const auto mask = static_cast<unsigned char>(1u << (position % CHAR_BIT));
            bytes[position / CHAR_BIT] = static_cast<unsigned char>((bytes[position / CHAR_BIT] & ~mask)
                | (((value >> bit) & 1) ? mask : 0));
        }
    }
    bool matches(const unsigned char *before, const unsigned char *after, size_t size, uint64_t value) const {
        if (read(after) != (value & maximum())) return false;
        for (size_t bit = 0; bit < size * CHAR_BIT; ++bit)
            if ((bit < first || bit >= first + width)
                    && ((before[bit / CHAR_BIT] ^ after[bit / CHAR_BIT]) & (1u << (bit % CHAR_BIT)))) return false;
        return true;
    }
};
template<size_t Size> static Mask calibrate(const std::array<unsigned char, Size> &zero,
                                           const std::array<unsigned char, Size> &ones) {
    Mask result;
    size_t end = 0;
    bool found = false;
    for (size_t bit = 0; bit < Size * CHAR_BIT; ++bit) {
        const auto mask = static_cast<unsigned char>(1u << (bit % CHAR_BIT));
        if (!((zero[bit / CHAR_BIT] ^ ones[bit / CHAR_BIT]) & mask)) continue;
        if ((zero[bit / CHAR_BIT] & mask) || !(ones[bit / CHAR_BIT] & mask))
            throw std::logic_error("The native bitfield has an unsupported object representation");
        if (!found) { result.first = bit; found = true; }
        end = bit;
        ++result.width;
    }
    if (!found || result.width > 64 || end - result.first + 1 != result.width)
        throw std::logic_error("The native bitfield is not a contiguous scalar field");
    return result;
}
template<class T> struct Reference {
    void *object;
    const Mask &mask;
    operator T() const {
        uint64_t value = mask.read(object);
        if constexpr (std::is_signed_v<T>)
            if (mask.width < 64 && (value & (uint64_t(1) << (mask.width - 1)))) value |= ~mask.maximum();
        return static_cast<T>(value);
    }
    Reference &operator=(T value) { mask.write(object, static_cast<uint64_t>(value)); return *this; }
};
} // namespace ProtectedFieldBits
