<?php

namespace App\Support;

use JsonException;

/** Reject duplicate object keys before PHP's JSON decoder can overwrite them. */
final class StrictJson
{
    private int $offset = 0;
    private int $depth = 0;

    private function __construct(private readonly string $source) {}

    public static function decodeObject(string $source): ?array
    {
        try {
            $parser = new self($source);
            $parser->space();
            $objectRoot = $parser->peek() === '{';
            $parser->value();
            $parser->space();
            if ($parser->offset !== strlen($source)) {
                return null;
            }
            if (!$objectRoot) {
                throw new \DomainException('Expected JSON object');
            }
            $decoded = json_decode($source, true, 32, JSON_THROW_ON_ERROR);
            return is_array($decoded) ? $decoded : null;
        } catch (JsonException | \UnexpectedValueException) {
            return null;
        }
    }

    public static function decodeTree(string $source): \stdClass
    {
        if (self::decodeObject($source) === null) {
            throw new \DomainException('Invalid JSON');
        }
        return json_decode($source, false, 32, JSON_THROW_ON_ERROR);
    }

    private function value(): void
    {
        if (++$this->depth > 32) {
            throw new \UnexpectedValueException();
        }
        $this->space();
        $start = $this->offset;
        $char = $this->peek();
        if ($char === '{') {
            $this->object();
        } elseif ($char === '[') {
            $this->array();
        } elseif ($char === '"') {
            $this->string();
        } else {
            while ($this->offset < strlen($this->source) && !str_contains(",]} \t\r\n", $this->source[$this->offset])) {
                $this->offset++;
            }
            $token = substr($this->source, $start, $this->offset - $start);
            json_decode($token, false, 32, JSON_THROW_ON_ERROR);
            if ($token === '') {
                throw new \UnexpectedValueException();
            }
        }
        $this->depth--;
    }

    private function object(): void
    {
        $this->offset++;
        $this->space();
        $keys = [];
        if ($this->take('}')) {
            return;
        }
        do {
            $this->space();
            $key = $this->string();
            if (isset($keys[$key])) {
                throw new \UnexpectedValueException();
            }
            $keys[$key] = true;
            $this->space();
            $this->require(':');
            $this->value();
            $this->space();
            if ($this->take('}')) {
                return;
            }
            $this->require(',');
        } while (true);
    }

    private function array(): void
    {
        $this->offset++;
        $this->space();
        if ($this->take(']')) {
            return;
        }
        do {
            $this->value();
            $this->space();
            if ($this->take(']')) {
                return;
            }
            $this->require(',');
        } while (true);
    }

    private function string(): string
    {
        if ($this->peek() !== '"') {
            throw new \UnexpectedValueException();
        }
        $start = $this->offset++;
        while ($this->offset < strlen($this->source)) {
            $char = $this->source[$this->offset++];
            if ($char === '"') {
                return json_decode(substr($this->source, $start, $this->offset - $start), true, 32, JSON_THROW_ON_ERROR);
            }
            if ($char === '\\') {
                $this->offset++;
            }
        }
        throw new \UnexpectedValueException();
    }

    private function space(): void
    {
        while ($this->offset < strlen($this->source) && str_contains(" \t\r\n", $this->source[$this->offset])) {
            $this->offset++;
        }
    }

    private function peek(): ?string
    {
        return $this->source[$this->offset] ?? null;
    }

    private function take(string $char): bool
    {
        if ($this->peek() === $char) {
            $this->offset++;
            return true;
        }
        return false;
    }

    private function require(string $char): void
    {
        if (!$this->take($char)) {
            throw new \UnexpectedValueException();
        }
    }
}
